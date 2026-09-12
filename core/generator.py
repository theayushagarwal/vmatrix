"""
core/generator.py
------------------
Turns a raw topic string into fully structured, ready-to-render JSON using
Gemini 2.5 Flash's native structured-output mode (response_mime_type =
"application/json"). No manual JSON-parsing gymnastics, no regex scraping of
markdown fences — the schema is enforced by the model itself.
"""

import os
import json
from google import genai
from google.genai import types
from .utils import retry_with_backoff, logger


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------
def get_gemini_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set. Add it to your .env file.")
    return genai.Client(api_key=api_key)


MODEL_NAME = "gemini-2.5-flash"


@retry_with_backoff(max_attempts=3, base_delay=2.0, exceptions=(Exception,))
def _call_gemini_json(client: genai.Client, contents: str, system_instruction: str, schema: dict, temperature: float) -> dict:
    """
    Single retried call to Gemini's structured-JSON mode. Self-healing here
    covers two common failure modes: transient API errors (rate limits,
    5xx, dropped connections) and, more rarely, a response that claims to be
    JSON but fails to parse — both get a fresh attempt with backoff instead
    of crashing the whole generation step on one bad response.
    """
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=temperature,
        ),
    )
    try:
        return json.loads(response.text)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("Gemini returned non-JSON response, will retry: %s", e)
        raise


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------
_CAROUSEL_SCHEMA = {
    "type": "object",
    "properties": {
        "series_title": {"type": "string"},
        "hook_line": {"type": "string"},
        "category": {
            "type": "string",
            "enum": ["AI & CODING", "FINANCE", "TOOLS"],
        },
        "slides": {
            "type": "array",
            "minItems": 5,
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["cover", "content", "outro"]},
                    "step_num": {"type": "string"},
                    "title": {"type": "string"},
                    "subtitle": {"type": "string"},
                    "description": {"type": "string"},
                    "key_benefit": {"type": "string"},
                    "tool_name": {"type": "string"},
                    "tool_domain": {"type": "string"},
                    "cta_keyword": {"type": "string"},
                    "action_text": {"type": "string"},
                },
                "required": ["type", "title"],
            },
        },
        "caption": {"type": "string"},
    },
    "required": ["series_title", "hook_line", "category", "slides", "caption"],
}

_CHEATSHEET_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "hook_line": {"type": "string"},
        "category": {
            "type": "string",
            "enum": ["AI & CODING", "FINANCE", "TOOLS"],
        },
        "items": {
            "type": "array",
            "minItems": 6,
            "maxItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "domain": {"type": "string"},
                    "desc": {"type": "string"},
                    "badge": {"type": "string"},
                },
                "required": ["name", "domain", "desc", "badge"],
            },
        },
        "caption": {"type": "string"},
    },
    "required": ["title", "hook_line", "category", "items", "caption"],
}


# --------------------------------------------------------------------------
# Prompts
# --------------------------------------------------------------------------
_CAROUSEL_SYSTEM_PROMPT = """You are an elite Instagram content strategist who writes viral,
high-value educational carousels for a page that covers AI & coding, personal finance, and
productivity tools. You write tight, punchy, zero-fluff copy that a busy professional would
actually stop scrolling for.

Given a TOPIC, produce a 5-slide carousel plan as JSON matching the provided schema, with this
exact slide sequence:

1. Slide 1 (type="cover"): a bold, scroll-stopping title, the hook_line, and a one-line subtitle
   that frames the value of the carousel.
2. Slides 2-4 (type="content"): three concrete steps or tools. Each needs a step_num ("01","02","03"),
   a short punchy title, a description of 25 words or fewer, a key_benefit badge (2-4 words,
   e.g. "SAVES 3 HRS/WK"), a tool_name, and a tool_domain (bare domain, e.g. "github.com") used
   to fetch a favicon. If the topic isn't tool-based, still invent a plausible representative
   tool/resource per step.
3. Slide 5 (type="outro"): a title that recaps the value, a cta_keyword (ONE short word/phrase,
   e.g. "CODE", "SAVE", "BUILD") that the audience should comment to get the resource, and an
   action_text describing what happens when they do (e.g. "Comment 'CODE' and I'll DM you the repo").

Also produce:
- series_title: a bold 3-5 word series name.
- category: one of "AI & CODING", "FINANCE", "TOOLS" — whichever best fits the topic.
- caption: a clean, scannable Instagram caption with short paragraphs, at most 2 emojis total,
  and exactly 5 targeted, relevant hashtags at the end.

Return ONLY valid JSON matching the schema. No markdown fences, no commentary.
"""

_CHEATSHEET_SYSTEM_PROMPT = """You are an elite Instagram content strategist who writes viral,
high-value single-image cheatsheets/comparison grids for a page covering AI & coding, personal
finance, and productivity tools.

Given a TOPIC, produce a single-page infographic plan as JSON matching the schema:
- title: bold 3-6 word headline.
- hook_line: catchy 6-10 word supporting line.
- category: one of "AI & CODING", "FINANCE", "TOOLS".
- items: exactly 6 cards, each with a name, a bare domain for a favicon (tool_domain style, e.g.
  "notion.so"), a desc of 12 words or fewer, and a badge (2-3 words status/label, e.g. "FREE TIER",
  "BEST VALUE", "PRO PICK").
- caption: a clean Instagram caption, short paragraphs, at most 2 emojis, 5 targeted hashtags.

Return ONLY valid JSON matching the schema. No markdown fences, no commentary.
"""


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------
def generate_carousel_content(topic: str) -> dict:
    """
    Generates structured JSON for a 5-slide educational carousel:
    - series_title: str (Bold 3-5 word title)
    - hook_line: str (Catchy 8-12 word hook)
    - category: str ('AI & CODING', 'FINANCE', or 'TOOLS')
    - slides: list of 5 slides:
        * Slide 1 (Cover): type='cover', title, hook_line, subtitle
        * Slides 2-4 (Content): type='content', step_num ('01','02','03'), title, description
          (max 25 words), key_benefit (badge), tool_name, tool_domain
        * Slide 5 (Outro): type='outro', title, cta_keyword (e.g. 'CODE'), action_text
    - caption: str (Clean Instagram caption with paragraphs, max 2 emojis, 5 targeted hashtags)
    """
    client = get_gemini_client()
    data = _call_gemini_json(
        client,
        contents=f"TOPIC: {topic}",
        system_instruction=_CAROUSEL_SYSTEM_PROMPT,
        schema=_CAROUSEL_SCHEMA,
        temperature=0.9,
    )

    # Defensive normalization: guarantee cover/outro carry hook_line/subtitle fields
    # even if the model omits them on individual slide objects.
    for slide in data.get("slides", []):
        if slide.get("type") == "cover":
            slide.setdefault("hook_line", data.get("hook_line", ""))
        if slide.get("type") == "content":
            slide.setdefault("step_num", "01")
        if slide.get("type") == "outro":
            slide.setdefault("cta_keyword", "MORE")

    return data


def generate_cheatsheet_content(topic: str) -> dict:
    """
    Generates structured single-page cheatsheet infographic data:
    - title, hook_line, category, items (list of 6 cards with name, domain, desc, badge)
    - caption: str
    """
    client = get_gemini_client()
    return _call_gemini_json(
        client,
        contents=f"TOPIC: {topic}",
        system_instruction=_CHEATSHEET_SYSTEM_PROMPT,
        schema=_CHEATSHEET_SCHEMA,
        temperature=0.9,
    )
