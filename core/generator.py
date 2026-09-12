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
from typing import Optional, Any
from dotenv import load_dotenv
from .utils import retry_with_backoff, logger

load_dotenv()

DEFAULT_GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
GEMINI_MODEL_NAME = "gemini-2.5-flash"


# --------------------------------------------------------------------------
# Clients
# --------------------------------------------------------------------------
def _get_groq_client() -> Optional[Any]:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        from groq import Groq
        return Groq(api_key=api_key)
    except Exception as e:
        logger.warning("Could not initialize Groq client: %s", e)
        return None


def get_gemini_client() -> Optional[genai.Client]:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception as e:
        logger.warning("Could not initialize Gemini client: %s", e)
        return None


@retry_with_backoff(max_attempts=3, base_delay=2.0, exceptions=(Exception,))
def _call_groq_json(client: Any, system_prompt: str, user_content: str, temperature: float = 0.7) -> dict:
    """
    Retried call to Groq with openai/gpt-oss-120b using native json_object mode.
    """
    completion = client.chat.completions.create(
        model=DEFAULT_GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        temperature=temperature,
    )
    content = completion.choices[0].message.content
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("Groq returned non-JSON response, will retry: %s", e)
        raise


@retry_with_backoff(max_attempts=3, base_delay=2.0, exceptions=(Exception,))
def _call_gemini_json(client: genai.Client, contents: str, system_instruction: str, schema: dict, temperature: float) -> dict:
    """
    Single retried call to Gemini's structured-JSON mode.
    """
    response = client.models.generate_content(
        model=GEMINI_MODEL_NAME,
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


_GROQ_CAROUSEL_PROMPT = _CAROUSEL_SYSTEM_PROMPT + """

You MUST return ONLY valid JSON matching this exact structure:
{
  "series_title": "string (3-5 words)",
  "hook_line": "string (catchy 8-12 word hook)",
  "category": "AI & CODING" or "FINANCE" or "TOOLS",
  "slides": [
    {
      "type": "cover",
      "title": "string",
      "hook_line": "string",
      "subtitle": "string"
    },
    {
      "type": "content",
      "step_num": "01",
      "title": "string",
      "description": "string (<=25 words)",
      "key_benefit": "string (2-4 words)",
      "tool_name": "string",
      "tool_domain": "bare domain e.g. cursor.com"
    },
    {
      "type": "content",
      "step_num": "02",
      "title": "string",
      "description": "string (<=25 words)",
      "key_benefit": "string (2-4 words)",
      "tool_name": "string",
      "tool_domain": "bare domain"
    },
    {
      "type": "content",
      "step_num": "03",
      "title": "string",
      "description": "string (<=25 words)",
      "key_benefit": "string (2-4 words)",
      "tool_name": "string",
      "tool_domain": "bare domain"
    },
    {
      "type": "outro",
      "title": "string",
      "cta_keyword": "string (ONE word e.g. CODE)",
      "action_text": "string"
    }
  ],
  "caption": "string (clean Instagram caption with 5 hashtags)"
}
"""

_GROQ_CHEATSHEET_PROMPT = _CHEATSHEET_SYSTEM_PROMPT + """

You MUST return ONLY valid JSON matching this exact structure:
{
  "title": "string (3-6 words)",
  "hook_line": "string (6-10 words)",
  "category": "AI & CODING" or "FINANCE" or "TOOLS",
  "items": [
    {
      "name": "string",
      "domain": "bare domain e.g. notion.so",
      "desc": "string (<= 12 words)",
      "badge": "string (2-3 words e.g. FREE TIER, PRO PICK)"
    }
  ],
  "caption": "string (clean Instagram caption with 5 hashtags)"
}
The items array MUST have exactly 6 items.
"""


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------
def generate_carousel_content(topic: str) -> dict:
    """
    Generates structured JSON for a 5-slide educational carousel.
    Uses Groq (openai/gpt-oss-120b) as the primary ultra-fast generator,
    with automatic fallback to Gemini 2.5 Flash if configured.
    """
    data = None
    groq_client = _get_groq_client()

    # 1. Try Groq (Ultra-fast openai/gpt-oss-120b)
    if groq_client:
        try:
            data = _call_groq_json(
                groq_client,
                system_prompt=_GROQ_CAROUSEL_PROMPT,
                user_content=f"TOPIC: {topic}",
                temperature=0.7,
            )
        except Exception as e:
            logger.warning("Groq carousel generation failed, trying Gemini: %s", e)

    # 2. Try Gemini fallback
    if not data:
        gemini_client = get_gemini_client()
        if gemini_client:
            try:
                data = _call_gemini_json(
                    gemini_client,
                    contents=f"TOPIC: {topic}",
                    system_instruction=_CAROUSEL_SYSTEM_PROMPT,
                    schema=_CAROUSEL_SCHEMA,
                    temperature=0.9,
                )
            except Exception as e:
                logger.error("Gemini carousel generation failed: %s", e)
                raise

    if not data:
        raise ValueError(
            "Neither GROQ_API_KEY nor GEMINI_API_KEY could generate content. "
            "Please ensure GROQ_API_KEY is configured in your .env file."
        )

    # Defensive normalization: guarantee cover/outro carry hook_line/subtitle fields
    # and all slides are complete and properly formatted.
    slides = data.get("slides", [])
    if not slides:
        raise ValueError("Generated carousel data contains no slides.")

    # Ensure valid category
    cat = data.get("category", "AI & CODING").upper()
    if "FIN" in cat:
        data["category"] = "FINANCE"
    elif "TOOL" in cat:
        data["category"] = "TOOLS"
    else:
        data["category"] = "AI & CODING"

    step_counter = 1
    for slide in slides:
        stype = slide.get("type", "content")
        if stype == "cover":
            slide.setdefault("hook_line", data.get("hook_line", ""))
            slide.setdefault("subtitle", "A practical step-by-step breakdown.")
        elif stype == "content":
            slide.setdefault("step_num", f"{step_counter:02d}")
            step_counter += 1
            slide.setdefault("key_benefit", "PRO TIP")
            slide.setdefault("tool_name", "Tool")
            slide.setdefault("tool_domain", "github.com")
        elif stype == "outro":
            slide.setdefault("cta_keyword", "GUIDE")
            slide.setdefault("action_text", "Comment below and get the complete resource.")

    return data


def generate_cheatsheet_content(topic: str) -> dict:
    """
    Generates structured single-page cheatsheet infographic data:
    - title, hook_line, category, items (list of 6 cards with name, domain, desc, badge)
    - caption: str
    """
    data = None
    groq_client = _get_groq_client()

    if groq_client:
        try:
            data = _call_groq_json(
                groq_client,
                system_prompt=_GROQ_CHEATSHEET_PROMPT,
                user_content=f"TOPIC: {topic}",
                temperature=0.7,
            )
        except Exception as e:
            logger.warning("Groq cheatsheet generation failed, trying Gemini: %s", e)

    if not data:
        gemini_client = get_gemini_client()
        if gemini_client:
            data = _call_gemini_json(
                gemini_client,
                contents=f"TOPIC: {topic}",
                system_instruction=_CHEATSHEET_SYSTEM_PROMPT,
                schema=_CHEATSHEET_SCHEMA,
                temperature=0.9,
            )

    if not data:
        raise ValueError(
            "Neither GROQ_API_KEY nor GEMINI_API_KEY is available for cheatsheet generation."
        )

    # Defensive normalization for cheatsheet items
    items = data.get("items", [])
    for it in items:
        it.setdefault("domain", "github.com")
        it.setdefault("badge", "PRO PICK")
        it.setdefault("desc", "High-efficiency developer tool")

    return data
