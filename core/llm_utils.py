"""
core/llm_utils.py / llm_utils.py
--------------------------------
Secondary Brain & Compliance Utilities for QA Verification Engine:
- Secondary Brain multi-provider routing (Groq -> Cerebras -> Gemini)
- Brand System Persona & Mandatory Disclaimers
- Anti-Shadowban Heuristic Pre-Scans & Forbidden Patterns
"""

import os
import re
import json
import logging
import requests
from typing import Optional

logger = logging.getLogger("llm_utils")

# --------------------------------------------------------------------------
# Brand Persona & Compliance Constants
# --------------------------------------------------------------------------
DISCLAIMER = "⚠️ Disclaimer: For educational and informational purposes only."

BRAND_SYSTEM_PROMPT = (
    "You are the creative lead of @vmatrix.co, a premier Instagram brand covering AI engineering, "
    "developer tools, system architecture, and tech finance. "
    "Your audience consists of high-school students, beginner coders, college students, and rookie 'vibe coders'. "
    "Followers expect sharp, highly accessible, zero-fluff technical insights explained simply.\n\n"
    "COGNITIVE ACCESSIBILITY MANDATE:\n"
    "1. Explain every concept as if you are explaining a shortcut to a smart friend over coffee.\n"
    "2. Strict 'Sentence & Word Cap' (Rule 1):\n"
    "   - Step headline: strictly maximum 6 words.\n"
    "   - what_it_is: strictly 1 sentence (strictly 10 to 18 words).\n"
    "   - why_it_matters: strictly 1 sentence (strictly 10 to 15 words).\n"
    "   - description: strictly maximum 25 words.\n\n"
    "NEGATIVE PERSONA GUARDRAILS (Rule 4 - Banned Jargon vs Approved Plain Translation):\n"
    "[BANNED]: 'Decentralized consensus protocol throughput' -> [APPROVED]: 'How fast the network agrees on a transaction'\n"
    "[BANNED]: 'Container isolation daemon abstraction' -> [APPROVED]: 'A lightweight box that lets code run anywhere'\n"
    "[BANNED]: 'Dollar-cost averaging with compound alpha' -> [APPROVED]: 'Investing $50 every Monday so you never buy at the peak'\n"
    "[BANNED]: 'Asynchronous non-blocking event loop' -> [APPROVED]: 'Doing 5 tasks at once without waiting for each one to finish'\n"
    "[BANNED]: Banned buzzwords: 'paradigm shift', 'leverage synergies', 'revolutionizing the landscape', "
    "'dive deep', 'game-changer', 'unleash the power', 'tapestry of', 'delve into'.\n"
    "Default tone: energetic, punchy, beginner-friendly, visual, and technically accurate."
)

FORBIDDEN_HASHTAGS = {
    "#followme", "#likeforlike", "#f4f", "#follow4follow", "#instadaily",
    "#instagood", "#tagsforlikes", "#like4like", "#instalike", "#followforfollow",
    "#sub4sub", "#gaintrick", "#gainparty", "#followback"
}

SHADOWBAN_TRIGGER_PHRASES = [
    "guaranteed return",
    "100% return",
    "10x return",
    "buy now",
    "get rich quick",
    "free money",
    "crypto giveaway",
    "dm me for info",
    "pump and dump",
    "double your money",
    "passive income secret",
    "instant profit",
    "risk-free investment",
    "click link in bio to buy",
]


def passes_shadowban_check(caption: str) -> bool:
    """
    Scans caption for financial/spam shadowban triggers and banned engagement hashtags.
    Returns False if any violation is detected; otherwise True.
    """
    if not caption:
        return True

    caption_lower = caption.lower()

    # 1. Phrase triggers
    for phrase in SHADOWBAN_TRIGGER_PHRASES:
        if phrase in caption_lower:
            logger.warning("Shadowban violation detected: trigger phrase '%s' found", phrase)
            return False

    # 2. Forbidden hashtags
    words = caption_lower.split()
    for word in words:
        clean_word = word.strip(",.!?\"'();:")
        if clean_word in FORBIDDEN_HASHTAGS:
            logger.warning("Shadowban violation detected: forbidden hashtag '%s' found", clean_word)
            return False

    return True


# --------------------------------------------------------------------------
# Secondary Brain Multi-Provider Calling (Groq -> Cerebras -> Gemini)
# --------------------------------------------------------------------------
def call_secondary_brain(
    prompt: str,
    temperature: float = 0.1,
    response_mime_type: str = "application/json",
    system_prompt: Optional[str] = None,
) -> Optional[str]:
    """
    Calls Secondary Brain LLM with fast Groq -> Cerebras -> Gemini failover.
    Supports structured JSON responses.
    """
    sys_prompt = system_prompt or BRAND_SYSTEM_PROMPT
    is_json = response_mime_type == "application/json"

    # 1. Try Groq (Llama-3.3-70b / gpt-oss-120b)
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        try:
            from groq import Groq
            client = Groq(api_key=groq_key)
            model = os.environ.get("GROQ_AUDIT_MODEL") or os.environ.get("GROQ_MODEL") or "openai/gpt-oss-120b"

            kwargs = {
                "model": model,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
                "max_tokens": 500,
            }
            if is_json:
                kwargs["response_format"] = {"type": "json_object"}

            resp = client.chat.completions.create(**kwargs)
            content = resp.choices[0].message.content
            if content and content.strip():
                return content.strip()
        except Exception as e:
            logger.debug("Groq secondary brain call failed: %s", e)

    # 2. Try Cerebras
    cerebras_key = os.environ.get("CEREBRAS_API_KEY")
    if cerebras_key:
        models = [os.environ.get("CEREBRAS_MODEL", "gpt-oss-120b"), "qwen-3.8-27b"]
        for m in models:
            try:
                headers = {
                    "Authorization": f"Bearer {cerebras_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": m,
                    "messages": [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": temperature,
                    "max_tokens": 500,
                }
                if is_json:
                    payload["response_format"] = {"type": "json_object"}

                r = requests.post(
                    "https://api.cerebras.ai/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=15,
                )
                if r.status_code == 200:
                    data = r.json()
                    res_content = data["choices"][0]["message"]["content"]
                    if res_content and res_content.strip():
                        return res_content.strip()
            except Exception as e:
                logger.debug("Cerebras (%s) secondary brain error: %s", m, e)

    # 3. Fallback to Gemini 2.5 Flash
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=gemini_key)
            config = types.GenerateContentConfig(
                temperature=temperature,
                response_mime_type="application/json" if is_json else "text/plain",
            )
            g_resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"{sys_prompt}\n\n{prompt}",
                config=config,
            )
            if g_resp.text:
                return g_resp.text.strip()
        except Exception as e:
            logger.warning("Gemini secondary brain fallback failed: %s", e)

    return None


# --------------------------------------------------------------------------
# Rule 5: Secondary Brain "Jargon Eraser" & Local Fallback
# --------------------------------------------------------------------------
JARGON_REPLACEMENTS = {
    r"\bparadigm shift\b": "game-changing shift",
    r"\bleverage synergies\b": "work together seamlessly",
    r"\brevolutionizing the landscape\b": "transforming how we build",
    r"\bdive deep\b": "break down",
    r"\bdelve into\b": "explore",
    r"\bunleash the power\b": "supercharge",
    r"\bgame-changer\b": "breakthrough",
    r"\btapestry of\b": "collection of",
    r"\bdecentralized consensus protocol throughput\b": "how fast the network agrees on transactions",
    r"\bcontainer isolation daemon abstraction\b": "a lightweight box that lets code run anywhere",
    r"\bdollar-cost averaging with compound alpha\b": "investing a fixed amount every week",
    r"\basynchronous non-blocking event loop\b": "running multiple tasks without waiting for each one",
}


def sanitize_jargon_local(text: str) -> str:
    """Fast deterministic local sanitizer for banned corporate & academic jargon."""
    if not text:
        return ""
    result = text
    for pattern, replacement in JARGON_REPLACEMENTS.items():
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def erase_jargon_with_secondary_brain(content_plan: dict) -> dict:
    """
    Rule 5: Secondary Brain 'Jargon Eraser'.
    Passes generated content through Groq / Cerebras / Gemini Llama-3.3 audit to:
    1. Scrub corporate/academic jargon into plain English relatable metaphors.
    2. Enforce strict word caps (headline <= 6 words, what_it_is: 10-18 words, why_it_matters: 10-15 words).
    3. Ensure accessibility for high-school students and rookie vibe coders.
    """
    if not isinstance(content_plan, dict):
        return content_plan

    slides = content_plan.get("slides", [])
    if not slides:
        return content_plan

    # Extract only text fields to keep secondary brain token usage low and fast
    compact_slides = []
    for s in slides:
        stype = s.get("type", "content")
        compact_slides.append({
            "type": stype,
            "title": s.get("title") or s.get("headline", ""),
            "what_it_is": s.get("what_it_is", ""),
            "why_it_matters": s.get("why_it_matters", ""),
            "description": s.get("description", ""),
            "key_benefit": s.get("key_benefit", ""),
        })

    audit_prompt = (
        "You are an elite Instagram copywriter and design auditor for @vmatrix.co.\n"
        "ACCESSIBILITY RULE:\n"
        "Ensure the language is simple, clean, and engaging for high-school students, beginner coders, and rookie 'vibe coders'.\n"
        "Strip out any academic corporate jargon (e.g. 'paradigm shift', 'leverage synergies', 'revolutionizing the landscape').\n"
        "Explain the concept as if you are explaining a shortcut to a smart friend.\n"
        "HARD CONSTRAINTS (RULE 1):\n"
        "- Each step headline/title must be strictly maximum 6 words.\n"
        "- what_it_is must be exactly 1 sentence (strictly 10 to 18 words).\n"
        "- why_it_matters must be exactly 1 sentence (strictly 10 to 15 words).\n"
        "- Each step description must be strictly maximum 25 words.\n\n"
        f"Here are the content slides:\n{json.dumps(compact_slides, indent=2)}\n\n"
        "Rewrite the text fields to be 100% compliant and crystal clear. "
        "Return ONLY a JSON object: {\"slides\": [ ... ]} with the same number of items."
    )

    try:
        raw_res = call_secondary_brain(audit_prompt, temperature=0.2, response_mime_type="application/json")
        if raw_res:
            if "{" in raw_res and "}" in raw_res:
                json_part = raw_res[raw_res.find("{"):raw_res.rfind("}") + 1]
                audited = json.loads(json_part)
                audited_slides = audited.get("slides", [])
                if len(audited_slides) == len(slides):
                    for orig, refined in zip(slides, audited_slides):
                        if refined.get("title"):
                            orig["title"] = sanitize_jargon_local(refined["title"])
                            if "headline" in orig:
                                orig["headline"] = orig["title"]
                        if refined.get("what_it_is"):
                            orig["what_it_is"] = sanitize_jargon_local(refined["what_it_is"])
                        if refined.get("why_it_matters"):
                            orig["why_it_matters"] = sanitize_jargon_local(refined["why_it_matters"])
                        if refined.get("description"):
                            orig["description"] = sanitize_jargon_local(refined["description"])
                        if refined.get("key_benefit"):
                            orig["key_benefit"] = refined["key_benefit"]
                    logger.info("  ✓ Secondary Brain Jargon Eraser successfully scrubbed and refined %d slides.", len(slides))
                    return content_plan
    except Exception as e:
        logger.warning("Secondary brain jargon erasure failed (%s). Applying local sanitization fallback.", e)

    # Local fallback sanitization
    for s in slides:
        for k in ("title", "headline", "description", "what_it_is", "why_it_matters", "hook_line", "subtitle"):
            if s.get(k):
                s[k] = sanitize_jargon_local(s[k])

    return content_plan

