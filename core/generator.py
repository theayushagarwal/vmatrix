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
import requests
from google import genai
from google.genai import types
from typing import Optional, Any
from dotenv import load_dotenv
from .utils import retry_with_backoff, logger
from .llm_utils import erase_jargon_with_secondary_brain

load_dotenv()

DEFAULT_GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
DEFAULT_CEREBRAS_MODEL = os.environ.get("CEREBRAS_MODEL", "gpt-oss-120b")
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
    if os.environ.get("ENABLE_GEMINI", "false").lower() not in ("true", "1", "yes"):
        return None
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception as e:
        logger.warning("Could not initialize Gemini client: %s", e)
        return None


GROQ_MODELS_CHAIN = [
    os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
]


@retry_with_backoff(max_attempts=2, base_delay=1.0, exceptions=(Exception,))
def _call_groq_json(client: Any, system_prompt: str, user_content: str, temperature: float = 0.7) -> dict:
    """
    Calls Groq using native json_object mode with automatic multi-model failover:
    openai/gpt-oss-120b -> openai/gpt-oss-20b -> qwen/qwen3.8-27b.
    """
    last_err = None
    for model_candidate in GROQ_MODELS_CHAIN:
        try:
            completion = client.chat.completions.create(
                model=model_candidate,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                temperature=temperature,
            )
            content = completion.choices[0].message.content
            return json.loads(content)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("Groq (%s) non-JSON response: %s, attempting next model", model_candidate, e)
            last_err = e
        except Exception as e:
            logger.warning("Groq (%s) call failed: %s, attempting next model", model_candidate, e)
            last_err = e

    if last_err:
        raise last_err


def _call_cerebras_json(system_prompt: str, user_content: str, temperature: float = 0.7) -> Optional[dict]:
    """
    Tier 2 Failover: Calls Cerebras inference endpoint with OpenAI-compatible JSON mode.
    Models attempted: DEFAULT_CEREBRAS_MODEL -> qwen-3.8-27b -> gemma-4-31b -> llama-3.3-70b.
    """
    api_key = os.environ.get("CEREBRAS_API_KEY")
    if not api_key:
        return None

    url = "https://api.cerebras.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    candidates = [
        DEFAULT_CEREBRAS_MODEL,
        "qwen-3.8-27b",
        "gemma-4-31b",
        "llama-3.3-70b",
    ]
    seen = set()
    for model in candidates:
        if model in seen:
            continue
        seen.add(model)
        try:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "response_format": {"type": "json_object"},
                "temperature": temperature,
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=25)
            if resp.status_code == 200:
                data = resp.json()
                raw = data["choices"][0]["message"]["content"]
                return json.loads(raw)
            else:
                logger.warning("Cerebras (%s) returned HTTP %d: %s", model, resp.status_code, resp.text[:120])
        except Exception as e:
            logger.warning("Cerebras (%s) call error: %s", model, e)

    return None


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
                    "what_it_is": {"type": "string"},
                    "why_it_matters": {"type": "string"},
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


# Part 4: Structured Data Schema for Gemini 2.5 Flash
RICH_SLIDE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "theme": types.Schema(type=types.Type.STRING, description="'LIGHT' or 'DARK'"),
        "cover_title": types.Schema(type=types.Type.STRING),
        "cover_subtitle": types.Schema(type=types.Type.STRING),
        "cta_keyword": types.Schema(type=types.Type.STRING),
        "slides": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "headline": types.Schema(type=types.Type.STRING),
                    "description": types.Schema(type=types.Type.STRING),
                    "tools": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "name": types.Schema(type=types.Type.STRING),
                                "logo": types.Schema(type=types.Type.STRING, description="SimpleIcon slug, e.g. 'docker', 'python', 'github'")
                            },
                            required=["name", "logo"]
                        ),
                    ),
                    "diagram": types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "type": types.Schema(
                                type=types.Type.STRING,
                                description="'flowchart', 'stack', or 'grid'",
                            ),
                            "nodes": types.Schema(
                                type=types.Type.ARRAY,
                                items=types.Schema(type=types.Type.STRING),
                                description="List of 3 to 4 labels for the diagram"
                            ),
                        },
                        required=["type", "nodes"]
                    ),
                },
                required=["headline", "description", "diagram"]
            ),
        ),
    },
    required=["cover_title", "cover_subtitle", "slides", "theme", "cta_keyword"]
)


# --------------------------------------------------------------------------
# Prompts
# --------------------------------------------------------------------------
_CAROUSEL_SYSTEM_PROMPT = """You are an elite Instagram content strategist for @vmatrix.co who writes
viral, high-value educational carousels for high-school students, beginner coders, and rookie 'vibe coders'.
Your copy must be crystal-clear, instantly readable, and 100% fluff-free.

COGNITIVE ENGINEERING PRINCIPLES (MANDATORY):
1. RULE 1 - HARD SENTENCE & WORD CAPS (No Fluff Allowed):
   - Each step headline: strictly maximum 6 words (e.g. '01 // Docker Containerization').
   - what_it_is: strictly 1 sentence (strictly 10 to 18 words, simple jargon-free definition).
   - why_it_matters: strictly 1 sentence (strictly 10 to 15 words, real-world payoff/benefit).
   - description: strictly maximum 25 words (punchy takeaway).

2. RULE 4 - RELATABLE METAPHORS INSTEAD OF TECHNICAL JARGON:
   - Explain every concept as if you are explaining a shortcut to a smart friend over coffee.
   - BANNED ACADEMIC JARGON vs APPROVED RELATABLE METAPHORS:
     [BANNED]: 'Decentralized consensus protocol throughput' -> [APPROVED]: 'How fast the network agrees on a transaction'
     [BANNED]: 'Container isolation daemon abstraction' -> [APPROVED]: 'A lightweight box that lets code run anywhere'
     [BANNED]: 'Dollar-cost averaging with compound alpha' -> [APPROVED]: 'Investing $50 every Monday so you never buy at the peak'
     [BANNED]: 'Asynchronous non-blocking event loop' -> [APPROVED]: 'Doing 5 tasks at once without waiting for each one to finish'
     [BANNED]: Never use buzzwords: 'paradigm shift', 'leverage synergies', 'revolutionizing the landscape', 'dive deep', 'game-changer', 'delve into'.

Given a TOPIC, produce a 5-slide carousel plan as JSON matching the provided schema, with this exact sequence:
1. Slide 1 (type="cover"): a bold, scroll-stopping title (max 6 words), hook_line (8-12 words), and a one-line subtitle framing the guide.
2. Slides 2-4 (type="content"): three concrete steps or tools. Each needs step_num ("01","02","03"),
   headline/title (max 6 words), what_it_is (10-18 words), why_it_matters (10-15 words), description (<=25 words),
   key_benefit badge (2-4 words, e.g. "SAVES 3 HRS/WK"), tool_name, and tool_domain (bare domain e.g. "github.com").
3. Slide 5 (type="outro"): a recap title, cta_keyword (ONE short word e.g. "CODE", "FLOW", "BUILD"), and action_text.

Also produce:
- series_title: a bold 3-5 word series name.
- category: one of "AI & CODING", "FINANCE", "TOOLS".
- caption: a clean, scannable Instagram caption with short paragraphs, at most 2 emojis total, and exactly 5 targeted hashtags at the end.

Return ONLY valid JSON matching the schema. No markdown fences, no commentary.
"""

_CHEATSHEET_SYSTEM_PROMPT = """You are an elite Instagram content strategist who writes viral,
high-value single-image cheatsheets/comparison grids for a page covering AI & coding, personal
finance, and productivity tools for beginner coders and students.

Given a TOPIC, produce a single-page infographic plan as JSON matching the schema:
- title: bold 3-6 word headline.
- hook_line: catchy 6-10 word supporting line.
- category: one of "AI & CODING", "FINANCE", "TOOLS".
- items: exactly 6 cards, each with a name, a bare domain for a favicon (tool_domain style, e.g.
  "notion.so"), a desc of strictly 12 words or fewer (simple plain English), and a badge (2-3 words status/label, e.g. "FREE TIER",
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
      "title": "string (strictly max 6 words)",
      "hook_line": "string",
      "subtitle": "string"
    },
    {
      "type": "content",
      "step_num": "01",
      "title": "string (strictly max 6 words)",
      "what_it_is": "string (strictly 1 sentence, 10 to 18 words, simple jargon-free definition)",
      "why_it_matters": "string (strictly 1 sentence, 10 to 15 words, real-world benefit/payoff)",
      "description": "string (strictly max 25 words)",
      "key_benefit": "string (2-4 words)",
      "tool_name": "string",
      "tool_domain": "bare domain e.g. cursor.com"
    },
    {
      "type": "content",
      "step_num": "02",
      "title": "string (strictly max 6 words)",
      "what_it_is": "string (strictly 1 sentence, 10 to 18 words, simple jargon-free definition)",
      "why_it_matters": "string (strictly 1 sentence, 10 to 15 words, real-world benefit/payoff)",
      "description": "string (strictly max 25 words)",
      "key_benefit": "string (2-4 words)",
      "tool_name": "string",
      "tool_domain": "bare domain"
    },
    {
      "type": "content",
      "step_num": "03",
      "title": "string (strictly max 6 words)",
      "what_it_is": "string (strictly 1 sentence, 10 to 18 words, simple jargon-free definition)",
      "why_it_matters": "string (strictly 1 sentence, 10 to 15 words, real-world benefit/payoff)",
      "description": "string (strictly max 25 words)",
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
            logger.warning("Groq carousel generation failed, trying Cerebras failover: %s", e)

    # 2. Try Cerebras failover (Instant Backup Editor - Tier 2)
    if not data:
        try:
            data = _call_cerebras_json(
                system_prompt=_GROQ_CAROUSEL_PROMPT,
                user_content=f"TOPIC: {topic}",
                temperature=0.7,
            )
            if data:
                logger.info("  ✓ Generated carousel content via Cerebras failover")
        except Exception as e:
            logger.warning("Cerebras carousel generation failed, trying Gemini: %s", e)

    # 3. Try Gemini fallback (Dormant Reserve - Tier 5)
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
            "Neither Groq, Cerebras, nor Gemini could generate content. "
            "Please ensure GROQ_API_KEY or CEREBRAS_API_KEY is configured in your .env file."
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
            if not slide.get("what_it_is"):
                desc = slide.get("description", "A lightweight developer tool that streamlines your workflow.")
                slide["what_it_is"] = desc
            if not slide.get("why_it_matters"):
                benefit = slide.get("key_benefit", "Saves developer time")
                slide["why_it_matters"] = f"Eliminates hours of manual boilerplate work: {benefit}."
        elif stype == "outro":
            slide.setdefault("cta_keyword", "GUIDE")
            slide.setdefault("action_text", "Comment below and get the complete resource.")

    # Rule 5: Pass through Secondary Brain Jargon Eraser
    try:
        data = erase_jargon_with_secondary_brain(data)
    except Exception as e:
        logger.warning("Jargon eraser pass encountered warning: %s", e)

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
            logger.warning("Groq cheatsheet generation failed, trying Cerebras failover: %s", e)

    # 2. Try Cerebras failover (Instant Backup Editor - Tier 2)
    if not data:
        try:
            data = _call_cerebras_json(
                system_prompt=_GROQ_CHEATSHEET_PROMPT,
                user_content=f"TOPIC: {topic}",
                temperature=0.7,
            )
            if data:
                logger.info("  ✓ Generated cheatsheet content via Cerebras failover")
        except Exception as e:
            logger.warning("Cerebras cheatsheet generation failed, trying Gemini: %s", e)

    # 3. Try Gemini fallback (Dormant Reserve - Tier 5)
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
            "Neither Groq, Cerebras, nor Gemini is available for cheatsheet generation."
        )

    # Defensive normalization for cheatsheet items
    items = data.get("items", [])
    for it in items:
        it.setdefault("domain", "github.com")
        it.setdefault("badge", "PRO PICK")
        it.setdefault("desc", "High-efficiency developer tool")

    return data


_GROQ_FLOW_PROMPT = """You are an elite system architect and technical Instagram creator for @vmatrix.co.
Given a technical TOPIC, produce a complete System Architecture Flowchart Carousel plan as JSON.

COGNITIVE ENGINEERING PRINCIPLES (MANDATORY):
1. RULE 1 - HARD SENTENCE & WORD CAPS:
   - Each slide 'headline': strictly maximum 6 words (e.g. '01 // Docker Containerization').
   - 'description': strictly 1 sentence (strictly 10 to 18 words, max 25 words).
   - Each diagram node: 2-3 words.
2. RULE 2 - 3-TIER VISUAL BRAIN ANCHOR:
   - Tier 1: Big Bold Hook (headline, max 6 words).
   - Tier 2: Interactive diagram (flowchart, stack, or grid) with 3-4 steps and tools with SimpleIcon logos.
   - Tier 3: One-sentence description + active stack.
3. RULE 4 - RELATABLE METAPHORS:
   - Write for high-school students, beginner coders, and rookie 'vibe coders'.
   - Avoid dense corporate/academic jargon. Explain concepts using real-world analogies.

EXACT JSON SCHEMA REQUIRED:
{
  "theme": "LIGHT" | "DARK",
  "series_title": "string (3-5 words, e.g. SYSTEM BLUEPRINT)",
  "cover_title": "string (bold headline, max 6 words)",
  "cover_subtitle": "string (punchy subtitle, 8-14 words)",
  "category": "AI & CODING" | "TOOLS" | "FINANCE",
  "cta_keyword": "string (ONE word e.g. FLOW or GUIDE)",
  "tools": [
    {"name": "string", "logo": "simpleicon-slug e.g. docker, fastapi, groq, redis, python, github"}
  ],
  "slides": [
    {
      "headline": "string (strictly max 6 words, e.g. Ingestion & WebSocket Gateway)",
      "description": "string (strictly 1 sentence, 10 to 18 words, max 25 words)",
      "tools": [
        {"name": "string", "logo": "simpleicon-slug"}
      ],
      "diagram": {
        "type": "flowchart" | "stack" | "grid",
        "nodes": ["string (step 1)", "string (step 2)", "string (step 3)", "string (step 4)"]
      },
      "active_node_name": "string (e.g. API Gateway)",
      "status_badge": "string (e.g. LATENCY < 15MS or STREAMING)",
      "nodes": [
        {"name": "string", "role": "string", "domain": "domain.com", "is_active": boolean}
      ],
      "bullets": [
        "string (concrete architecture spec)",
        "string (concrete architecture spec)",
        "string (concrete architecture spec)"
      ]
    }
  ],
  "outro": {
    "title": "string (e.g. Ready to Deploy This Pipeline?)",
    "cta_keyword": "string (ONE word)",
    "action_text": "string (e.g. Comment 'FLOW' and I will DM you the complete architecture repo & setup instructions.)"
  },
  "caption": "string (clean Instagram caption with exactly 5 hashtags)"
}

Rules:
1. 'slides' array MUST contain exactly 3 technical flow steps (representing step 1, 2, 3 of the pipeline).
2. 'diagram' object inside each slide MUST have 'type' ('flowchart', 'stack', or 'grid') and 'nodes' (list of 3-4 concise step names).
3. 'tools' array MUST contain 3-4 key tools with SimpleIcon slugs in 'logo' (e.g. 'docker', 'python', 'github', 'fastapi', 'redis', 'postgresql', 'supabase', 'nextdotjs', 'nginx').
4. Return ONLY valid JSON.
"""


def generate_flow_carousel_content(topic: str) -> dict:
    """
    Generates structured system architecture flowchart carousel plan:
    - theme: 'LIGHT' or 'DARK'
    - series_title, cover_title, cover_subtitle, category, cta_keyword
    - tools: 4 key tools/frameworks with SimpleIcon slugs
    - slides: 3 concrete pipeline flow steps with diagram (flowchart/stack/grid) and specs
    - outro: CTA keyword and action text
    - caption: Instagram caption
    """
    data = None
    groq_client = _get_groq_client()

    if groq_client:
        try:
            data = _call_groq_json(
                groq_client,
                system_prompt=_GROQ_FLOW_PROMPT,
                user_content=f"TOPIC: {topic}",
                temperature=0.7,
            )
        except Exception as e:
            logger.warning("Groq flow carousel generation failed, trying Cerebras failover: %s", e)

    # 2. Try Cerebras failover (Instant Backup Editor - Tier 2)
    if not data:
        try:
            data = _call_cerebras_json(
                system_prompt=_GROQ_FLOW_PROMPT,
                user_content=f"TOPIC: {topic}",
                temperature=0.7,
            )
            if data:
                logger.info("  ✓ Generated flow carousel content via Cerebras failover")
        except Exception as e:
            logger.warning("Cerebras flow carousel generation failed, trying Gemini: %s", e)

    # 3. Try Gemini fallback (Dormant Reserve - Tier 5)
    if not data:
        gemini_client = get_gemini_client()
        if gemini_client:
            try:
                data = _call_gemini_json(
                    gemini_client,
                    contents=f"TOPIC: {topic}",
                    system_instruction=_GROQ_FLOW_PROMPT,
                    schema=RICH_SLIDE_SCHEMA,
                    temperature=0.7,
                )
            except Exception as e:
                logger.error("Gemini flow carousel generation failed: %s", e)

    if not data:
        raise ValueError("Neither Groq, Cerebras, nor Gemini could generate flow carousel content. Check your API keys in .env.")

    # Defensive normalization
    data.setdefault("theme", "LIGHT")
    data.setdefault("series_title", "SYSTEM ARCHITECTURE")
    data.setdefault("cover_title", topic)
    data.setdefault("cover_subtitle", "Complete Step-by-Step Technical Blueprint")
    data.setdefault("cta_keyword", "FLOW")
    data.setdefault("category", "AI & CODING")

    tools = data.get("tools", [])
    if not tools:
        data["tools"] = [
            {"name": "FastAPI", "logo": "fastapi", "domain": "fastapi.tiangolo.com"},
            {"name": "Groq", "logo": "groq", "domain": "groq.com"},
            {"name": "Supabase", "logo": "supabase", "domain": "supabase.com"},
            {"name": "Docker", "logo": "docker", "domain": "docker.com"}
        ]
    else:
        for t in tools:
            if isinstance(t, dict):
                t.setdefault("logo", t.get("name", "github").lower().replace(" ", "").replace(".", ""))

    slides = data.get("slides", [])
    if not slides:
        raise ValueError("Flow carousel generated 0 flow slides.")

    for idx, s in enumerate(slides):
        s.setdefault("headline", f"Phase {idx+1}: Architecture Flow")
        s.setdefault("description", "Pipeline processing step.")

        # Normalize diagram
        diagram = s.get("diagram")
        if not diagram or not isinstance(diagram, dict):
            existing_nodes = s.get("nodes", [])
            node_names = [n.get("name", str(n)) if isinstance(n, dict) else str(n) for n in existing_nodes] if existing_nodes else ["Input", "Process", "Output"]
            diagram_types = ["flowchart", "stack", "grid"]
            s["diagram"] = {
                "type": diagram_types[idx % len(diagram_types)],
                "nodes": node_names
            }
        else:
            diagram.setdefault("type", "flowchart")
            if "nodes" not in diagram or not diagram["nodes"]:
                diagram["nodes"] = ["Input", "Process", "Output"]

        # Backwards compatible nodes list
        if not s.get("nodes"):
            s["nodes"] = [
                {"name": n, "role": "Component", "domain": "github.com", "is_active": i == 0}
                for i, n in enumerate(s["diagram"]["nodes"])
            ]

        s.setdefault("active_node_name", s["diagram"]["nodes"][0] if s["diagram"]["nodes"] else f"Node {idx+1}")
        s.setdefault("status_badge", "ACTIVE")
        s.setdefault("bullets", [
            "High-throughput asynchronous event handling",
            "Low-latency streaming payload serialization",
            "Automatic connection pooling with graceful backoff"
        ])
        if not s.get("tools"):
            s["tools"] = data["tools"][:2]

    outro = data.setdefault("outro", {})
    outro.setdefault("title", "Ready to Build This Pipeline?")
    outro.setdefault("cta_keyword", data.get("cta_keyword", "FLOW"))
    outro.setdefault("action_text", f"Comment '{data.get('cta_keyword', 'FLOW')}' and I'll DM you the complete starter repo.")

    # Rule 5: Pass through Secondary Brain Jargon Eraser
    try:
        data = erase_jargon_with_secondary_brain(data)
    except Exception as e:
        logger.warning("Flow jargon eraser pass encountered warning: %s", e)

    return data


def generate_rich_flow_content(topic: str, theme: str = "LIGHT") -> dict:
    """
    Generates structured system architecture flowchart carousel plan
    matching the RICH_SLIDE_SCHEMA with selectable theme ('LIGHT' or 'DARK').
    """
    data = generate_flow_carousel_content(topic)
    data["theme"] = theme
    return data
