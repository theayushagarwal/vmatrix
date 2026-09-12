"""
core/caption.py
---------------
Auto-Caption Generation Engine:
Generates high-performing, niche-targeted, engagement-optimized Instagram captions
using a 3-Stage Multi-AI Pipeline:

Stage 1: Dynamic Niche & Hashtag Routing (PURE_AI, PURE_FINANCE, MIXED)
Stage 2: Structured Multi-Voice Drafting with Groq & Cerebras (5 Rotating Personas)
Stage 3: Secondary Brain Brand Audit & Polish (Zero wall-of-text, max 3 emojis,
         no literal layout descriptions, anti-shadowban hashtag assembly)
"""

import os
import re
import json
import time
from typing import Optional, Dict, Any, List
import requests

from .utils import retry_with_backoff, logger

# --------------------------------------------------------------------------
# Persona Voices
# --------------------------------------------------------------------------
VOICES = [
    ("Punchy", "Write a punchy, short, high-impact Instagram caption with sharp spacing."),
    ("Listicle", "Write an engaging Instagram caption structured as 3 actionable takeaways or tips."),
    ("Storytelling", "Write an engaging Instagram caption with a brief narrative arc, explaining the developer breakthrough or workflow transformation."),
    ("Question-Hook", "Write an engaging Instagram caption starting with a provocative question hook to spark comments."),
    ("Stat-Led", "Write an engaging Instagram caption highlighting an eye-opening benchmark, latency metric, or engineering stat.")
]

# --------------------------------------------------------------------------
# Curated Niche Hashtag Pools
# --------------------------------------------------------------------------
NICHE_HASHTAG_POOLS = {
    "PURE_AI": [
        "#ai #programming #coding #developer #softwareengineer #webdev #datascience #python #machinelearning #techtools #softwaredevelopment #techcheatsheet #vibecoder #claude",
        "#codinglife #programmer #learntocode #computerscience #github #vscode #webdevelopment #aiagent #softwaredev #tech #javascript #devcommunity"
    ],
    "PURE_FINANCE": [
        "#finance #investing #stocks #stockmarket #personalfinance #wealthbuilding #compoundinterest #financialfreedom #passiveincome #indexfunds #sandp500 #moneytips #invest",
        "#financialliteracy #wealthcoach #investmenttips #portfoliomanagement #moneymanagement #budgeting #investor #smartmoney #financialplanning"
    ],
    "MIXED": [
        "#fintech #aifinance #algorithmictrading #wealthtech #smartinvesting #investingtools #pythonfinance #stockanalysis #automatedinvesting #aiinvesting #quantfinance",
        "#financeai #predictiveanalytics #innovation #techtrends #datascience #smartinvesting #financialfreedom #ai #techinvesting"
    ]
}

# Forbidden Hashtags (Blocks shadowbans & low-quality spam tags)
FORBIDDEN_HASHTAGS = {
    "#followme", "#likeforlike", "#f4f", "#follow4follow", "#instadaily",
    "#instagood", "#tagsforlikes", "#like4like", "#instalike", "#followforfollow"
}

# Brand Persona & Safety Guardrails
DISCLAIMER = "⚠️ Disclaimer: For educational and informational purposes only."

BRAND_SYSTEM_PROMPT = (
    "You are the creative lead of @vmatrix.co, a premier Instagram brand covering AI engineering, "
    "developer tools, system architecture, and tech finance. "
    "Your audience consists of analytically curious developers, tech enthusiasts, researchers, and students. "
    "Followers expect sharp, highly specific, technical insights. "
    "Avoid generic AI clichés (e.g., 'dive deep', 'game-changer', 'revolutionizing the world'). "
    "Focus on concrete utility, workflow shortcuts, latency metrics, or code mechanics. "
    "Default tone: confident, precise, beginner-friendly yet technically sound."
)


# --------------------------------------------------------------------------
# Helpers: Niche Routing & Text Sanitation
# --------------------------------------------------------------------------
def determine_niche(text: str) -> str:
    """Classifies topic text into PURE_AI, PURE_FINANCE, or MIXED."""
    text_lower = text.lower()
    has_finance = any(w in text_lower for w in [
        "finance", "invest", "stock", "portfolio", "interest", "wealth",
        "saving", "return", "asset", "money", "rupee", "dollar", "crypto", "trading"
    ])
    has_tech = any(w in text_lower for w in [
        "ai", "gpt", "claude", "gemini", "bot", "automate", "python",
        "code", "agent", "llm", "pipeline", "docker", "developer", "api"
    ])

    if has_finance and has_tech:
        return "MIXED"
    elif has_finance:
        return "PURE_FINANCE"
    return "PURE_AI"


def clean_hashtags(caption_text: str) -> str:
    """Strips shadowbanned and spammy engagement hashtags."""
    cleaned_words = []
    for word in caption_text.split():
        if word.lower() in FORBIDDEN_HASHTAGS:
            continue
        cleaned_words.append(word)
    return " ".join(cleaned_words)


def assemble_caption(body: str, hashtag_pool: str) -> str:
    """Joins body copy, disclaimer, and hashtag pool with clean double-line breaks."""
    body_clean = body.strip()
    return f"{body_clean}\n\n{DISCLAIMER}\n\n{hashtag_pool}"


# --------------------------------------------------------------------------
# Multi-AI Text Generation (Groq -> Cerebras -> Gemini)
# --------------------------------------------------------------------------
def _call_llm_text(system_prompt: str, user_prompt: str, temperature: float = 0.7) -> Optional[str]:
    """Fast text generation with automatic Groq -> Cerebras failover."""
    # 1. Try Groq
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        try:
            from groq import Groq
            client = Groq(api_key=groq_key)
            model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=350,
            )
            text = resp.choices[0].message.content
            if text and text.strip():
                return text.strip()
        except Exception as e:
            logger.warning("Groq text generation failed for caption: %s", e)

    # 2. Try Cerebras Failover
    cerebras_key = os.environ.get("CEREBRAS_API_KEY")
    if cerebras_key:
        for m in [os.environ.get("CEREBRAS_MODEL", "gpt-oss-120b"), "qwen-3.8-27b", "llama-3.3-70b"]:
            try:
                r = requests.post(
                    "https://api.cerebras.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {cerebras_key}", "Content-Type": "application/json"},
                    json={
                        "model": m,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": temperature,
                        "max_tokens": 350,
                    },
                    timeout=20,
                )
                if r.status_code == 200:
                    data = r.json()
                    return data["choices"][0]["message"]["content"].strip()
            except Exception as e:
                logger.debug("Cerebras (%s) caption error: %s", m, e)

    # 3. Try Gemini Fallback (if enabled)
    if os.environ.get("ENABLE_GEMINI", "false").lower() in ("true", "1", "yes"):
        gemini_key = os.environ.get("GEMINI_API_KEY")
        if gemini_key:
            try:
                from google import genai
                g_client = genai.Client(api_key=gemini_key)
                g_resp = g_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=f"{system_prompt}\n\n{user_prompt}",
                )
                if g_resp.text:
                    return g_resp.text.strip()
            except Exception as e:
                logger.warning("Gemini caption error: %s", e)

    return None


# --------------------------------------------------------------------------
# Main Caption Pipeline (3-Stage Engine)
# --------------------------------------------------------------------------
def generate_caption(
    topic: str,
    context_summary: str = "",
    voice_index: int = 0,
    hashtag_index: int = 0,
) -> str:
    """
    3-Stage Instagram Caption Pipeline:
    1. Dynamic Niche & Hashtag Routing
    2. Structured Drafting via Primary Brain (Groq / Cerebras)
    3. Secondary Brain Brand Audit & Rewrite
    """
    voice_name, voice_instructions = VOICES[voice_index % len(VOICES)]
    niche = determine_niche(f"{topic} {context_summary}")
    niche_pools = NICHE_HASHTAG_POOLS.get(niche, NICHE_HASHTAG_POOLS["PURE_AI"])
    hashtag_pool = niche_pools[hashtag_index % len(niche_pools)]

    logger.info("  📝 Generating caption with voice '%s' (Niche: %s)...", voice_name, niche)

    # ── STAGE 1: DRAFTING VIA PRIMARY BRAIN ──────────────────────────────────
    draft_prompt = f"""Write an engaging, insightful Instagram caption (max 110 words) for @vmatrix.co.
Topic: {topic}
Details & Key Points: {context_summary or topic}

Voice Persona: {voice_name} - {voice_instructions}

CRITICAL RULES:
1. NO LITERAL IMAGE DESCRIPTIONS: Do NOT say 'look at this image/diagram', do not describe backgrounds or colors. Focus on the technical concept and practical developer takeaway.
2. NO WALL OF TEXT: Use clean double-line breaks (\\n\\n) between 2-3 short paragraphs.
3. EMOJI DENSITY: MAXIMUM 2-3 emojis in the entire text.
4. NO CALLS TO ACTION: Do NOT ask to follow, like, or save.
5. NO HASHTAGS IN BODY: Return plain text only. No hashtags.
"""

    draft = _call_llm_text(BRAND_SYSTEM_PROMPT, draft_prompt, temperature=0.8)

    if not draft:
        draft = f"{topic}\n\nA practical breakdown of essential tools and modern workflows to boost your development velocity. Check out the key architecture points above."

    # Strip any accidental hashtags from draft body
    draft_lines = []
    for line in draft.splitlines():
        words = [w for w in line.split() if not w.startswith("#")]
        if words:
            draft_lines.append(" ".join(words))
    clean_draft = "\n\n".join([p.strip() for p in "\n".join(draft_lines).split("\n\n") if p.strip()])

    # ── STAGE 2: SECONDARY BRAIN BRAND AUDIT & REWRITE ────────────────────────
    audit_prompt = f"""You are the senior editorial director for @vmatrix.co.
Review and polish this Instagram caption draft to ensure 10/10 quality:

---
{clean_draft}
---

Strict Checklist:
1. Paragraph breaks: Exactly 2-3 clean, punchy paragraphs separated by blank lines (\\n\\n).
2. Emojis: At most 2 tasteful tech emojis (e.g. ⚡, 🚀, 💻).
3. Zero fluff: Cut buzzwords like 'game-changer' or 'revolutionize'.
4. No hashtags: Keep body text 100% free of hashtags.
5. Accessible to students & junior developers without losing technical precision.

Reply with ONLY the polished caption text. No preamble, no quotes."""

    polished = _call_llm_text(BRAND_SYSTEM_PROMPT, audit_prompt, temperature=0.3)
    final_body = polished.strip().strip('"').strip("'") if polished else clean_draft

    # ── STAGE 3: ASSEMBLE WITH DISCLAIMER & HASHTAG POOL ──────────────────────
    final_caption = clean_hashtags(assemble_caption(final_body, hashtag_pool))
    return final_caption


def generate_listicle_caption(
    listicle_data: Dict[str, Any],
    voice_index: int = 0,
    hashtag_index: int = 0,
) -> str:
    """
    Generates a specialized caption tailored to a 5-slide educational carousel.
    Extracts concepts from each slide to make the caption ultra-specific.
    """
    series_title = listicle_data.get("series_title") or listicle_data.get("cover_title", "Developer Guide")
    slides = listicle_data.get("slides", [])

    concepts_summary = ""
    for idx, s in enumerate(slides):
        title = s.get("title") or s.get("headline", "")
        desc = s.get("description") or s.get("key_benefit", "")
        if title:
            concepts_summary += f"Slide {idx+1}: {title} — {desc}\n"

    return generate_caption(
        topic=series_title,
        context_summary=concepts_summary,
        voice_index=voice_index,
        hashtag_index=hashtag_index,
    )


def generate_post_caption(
    topic: str,
    content_plan: Dict[str, Any],
    format_type: str = "auto",
) -> str:
    """
    Unified entry point for generating captions across all formats (photo, listicle, flow).
    Rotates voice based on day-of-year so daily posts never sound repetitive.
    """
    day_of_year = int(time.strftime("%j"))
    voice_idx = day_of_year
    hashtag_idx = day_of_year % 2

    if format_type in ("listicle", "flow") or "slides" in content_plan:
        return generate_listicle_caption(content_plan, voice_index=voice_idx, hashtag_index=hashtag_idx)

    # For single photo cheatsheet:
    items = content_plan.get("items", [])
    items_summary = ", ".join([f"{it.get('name')}: {it.get('desc')}" for it in items[:4]])
    hook = content_plan.get("hook_line", "")

    return generate_caption(
        topic=topic,
        context_summary=f"{hook}\nKey tools covered: {items_summary}",
        voice_index=voice_idx,
        hashtag_index=hashtag_idx,
    )


def generate_post_comment(
    topic: str,
    content_plan: Optional[Dict[str, Any]] = None,
    format_type: str = "auto",
) -> str:
    """
    Generates a high-converting, engagement-driving first comment for the published post.
    Combines a technical discussion hook with a bookmark/save CTA.
    Uses Groq/Cerebras if available, with deterministic failover templates.
    """
    plan = content_plan or {}
    hook = plan.get("hook_line") or plan.get("cover_subtitle") or ""

    # Deterministic fallback templates based on format
    if format_type == "photo" or "items" in plan:
        fallback = (
            f"Which of these tools is your daily driver in 2026? Or did we miss an essential pick? "
            f"Drop your thoughts below! 👇\n\n📌 Bookmark this cheatsheet for your next project."
        )
    elif format_type == "flow":
        fallback = (
            f"How does your team handle this architecture in production? What's your biggest bottleneck? "
            f"Let's discuss below 👇\n\n📌 Save this architecture breakdown for your next system design review."
        )
    else:
        fallback = (
            f"Which of these key takeaways had the biggest impact on your developer workflow? "
            f"Drop a comment below! 👇\n\n📌 Save this guide so you can reference it anytime."
        )

    # Attempt LLM generation for maximum freshness & specificity
    prompt = (
        f"You are the creator of @vmatrix.co on Instagram. Write a short, high-engagement first comment "
        f"(max 35 words) to auto-post and pin under our new post on '{topic}'.\n"
        f"Context: {hook}\n\n"
        f"Instructions:\n"
        f"1. Ask our developer audience a specific, provocative question about their stack, workflow, or architectural choice to spark comments.\n"
        f"2. End with a clean one-line CTA to bookmark/save the post (e.g., '📌 Bookmark this for your next build.').\n"
        f"3. Max 2 emojis total. Plain text only. No hashtags. Do not include quotes."
    )

    try:
        res = _call_llm_text(BRAND_SYSTEM_PROMPT, prompt, temperature=0.7)
        if res and len(res.strip()) > 10:
            cleaned = res.strip().strip('"\'')
            return cleaned
    except Exception as e:
        logger.debug("LLM comment generation failed, using fallback: %s", e)

    return fallback

