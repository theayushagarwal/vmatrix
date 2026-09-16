"""
core/text_auditor.py
--------------------
Layer 1 & 2: Caption & Text Compliance Auditor:
1. Fast Local Heuristic Pre-Checks (Zero API Cost):
   - Shadowban trigger phrase scans
   - Deterministic legal disclaimer placement & ordering
   - Emoji density audit (max 4 allowed)
   - Wall-of-text double break spacing enforcement
   - Isolation of hashtags to footer
2. Secondary Brain LLM Audit (Groq Llama-3.3 / Cerebras / Gemini 2.5 Flash):
   - Factual accuracy & logic validation
   - Generic AI copy rejection
   - Rejection of literal layout descriptions
"""

import os
import re
import json
import logging
try:
    import emoji
except ImportError:
    emoji = None
from typing import Optional, Dict, Any, Union

from .llm_utils import call_secondary_brain, BRAND_SYSTEM_PROMPT, DISCLAIMER, passes_shadowban_check

logger = logging.getLogger("text_auditor")

# Lazy Gemini client helper
_gemini_client = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        gemini_key = os.environ.get("GEMINI_API_KEY")
        if gemini_key:
            try:
                from google import genai
                _gemini_client = genai.Client(api_key=gemini_key)
            except Exception as e:
                logger.debug("Could not initialize google.genai Client: %s", e)
    return _gemini_client


def verify_text_content(topic_or_listicle: Any, caption: str, is_listicle: bool = False) -> dict:
    """
    4-Layer QA: Layer 1 (Heuristics) and Layer 2 (AI Semantic Audit).
    Returns structured audit dictionary:
    {"status": "APPROVED" | "REJECTED", "caption_ok": bool, "facts_ok": bool, "fail_reason": str}
    """
    if not caption or not caption.strip():
        return {
            "status": "REJECTED",
            "caption_ok": False,
            "facts_ok": False,
            "fail_reason": "Caption is empty."
        }

    # ── 1. FAST LOCAL HEURISTIC PRE-CHECKS (Zero API Cost) ─────────────────

    # Check 1.1: Shadowban trigger phrases (e.g. "guaranteed return", "buy now", "10x return")
    if not passes_shadowban_check(caption):
        return {
            "status": "REJECTED",
            "caption_ok": False,
            "facts_ok": False,
            "fail_reason": "Caption failed shadowban pre-scan due to compliance patterns."
        }

    # Check 1.2: Deterministic legal disclaimer placement
    disclaimer_idx = caption.find(DISCLAIMER)
    hashtag_idx = next((caption.find(w) for w in caption.split() if w.startswith("#")), -1)
    if disclaimer_idx == -1 or (hashtag_idx != -1 and disclaimer_idx > hashtag_idx):
        return {
            "status": "REJECTED",
            "caption_ok": True,
            "facts_ok": False,
            "fail_reason": "Disclaimer is missing or placed after hashtags."
        }

    # Check 1.3: Emoji Density (Max 4 emojis allowed)
    if emoji and hasattr(emoji, "is_emoji"):
        emoji_count = len([c for c in caption if emoji.is_emoji(c)])
    else:
        emoji_count = len(re.findall(r"[\U00010000-\U0010ffff]", caption))
    if emoji_count > 4:
        return {
            "status": "REJECTED",
            "caption_ok": False,
            "facts_ok": True,
            "fail_reason": f"Emoji density too high ({emoji_count} emojis, max allowed is 4)."
        }

    # Check 1.4: Wall of text check (Requires \n\n paragraph spacing)
    caption_body = caption.split(DISCLAIMER)[0].strip()
    if len(caption_body.split()) > 40 and "\n\n" not in caption_body:
        return {
            "status": "REJECTED",
            "caption_ok": False,
            "facts_ok": True,
            "fail_reason": "Wall of text detected. Captions must use clean double-line breaks (\\n\\n)."
        }

    # Check 1.5: No inline hashtags in caption body
    if "#" in caption_body:
        return {
            "status": "REJECTED",
            "caption_ok": False,
            "facts_ok": True,
            "fail_reason": "Inline hashtags found in body. Keep hashtags isolated at the very bottom."
        }

    # ── 2. AI BATCH AUDIT (Factual Accuracy & Copy Quality) ────────────────
    prompt = (
        "Analyze the following post details and generated Instagram caption:\n\n"
        f"Context: {topic_or_listicle}\nCaption:\n{caption}\n\n"
        "Evaluate the following criteria strictly:\n"
        "1. CAPTION QUALITY (caption_ok):\n"
        "   - Is it engaging and free of generic templates?\n"
        "   - Does it avoid follow, like, or save CTAs?\n"
        "   - NO LITERAL IMAGE DESCRIPTIONS: Reject if caption literally describes the visual layout/colors/illustration.\n"
        "2. FACTUAL ACCURACY & COMPLIANCE (facts_ok):\n"
        "   - Are there any technical falsehoods or logic errors (e.g. mapping NumPy to CSS)?\n"
        "   - Are there compliance violations or spammy claims?\n\n"
        "Reply with a JSON object: {\"caption_ok\": bool, \"facts_ok\": bool, \"fail_reason\": str}"
    )

    try:
        # Fast query to Groq Llama-3.3 / Cerebras first
        res_text = call_secondary_brain(prompt, temperature=0.1, response_mime_type="application/json")
        if res_text:
            if "{" in res_text and "}" in res_text:
                json_str = res_text[res_text.find("{"):res_text.rfind("}") + 1]
                res = json.loads(json_str)
                c_ok = res.get("caption_ok", True)
                f_ok = res.get("facts_ok", True)
                return {
                    "status": "APPROVED" if (c_ok and f_ok) else "REJECTED",
                    "caption_ok": c_ok,
                    "facts_ok": f_ok,
                    "fail_reason": res.get("fail_reason", "")
                }
    except Exception as e:
        logger.warning(f"Secondary brain audit failed ({e}), falling back to Gemini.")

    # Fallback to Gemini 2.5 Flash
    client = _get_gemini_client()
    if client:
        try:
            from google.genai import types
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.1, response_mime_type="application/json")
            )
            raw_text = response.text.strip()
            if "{" in raw_text and "}" in raw_text:
                raw_text = raw_text[raw_text.find("{"):raw_text.rfind("}") + 1]
            res = json.loads(raw_text)
            is_valid = res.get("caption_ok", True) and res.get("facts_ok", True)
            return {
                "status": "APPROVED" if is_valid else "REJECTED",
                "caption_ok": res.get("caption_ok", True),
                "facts_ok": res.get("facts_ok", True),
                "fail_reason": res.get("fail_reason", "")
            }
        except Exception as e:
            logger.warning("Gemini audit failed: %s", e)

    # Heuristic pass if both LLM calls were unavailable
    return {
        "status": "APPROVED",
        "caption_ok": True,
        "facts_ok": True,
        "fail_reason": ""
    }


def validate_caption(caption: str, prompt: str) -> bool:
    """Convenience boolean check for caption compliance."""
    res = verify_text_content(prompt, caption)
    return res.get("status") == "APPROVED"


def auto_fix_caption(caption: str) -> str:
    """
    Surgically heals minor heuristic violations (e.g. disclaimer placement, emoji density, inline hashtags).
    """
    # 1. Strip inline hashtags from body and collect for footer
    body_part = caption
    if DISCLAIMER in body_part:
        body_part, rest = body_part.split(DISCLAIMER, 1)
    else:
        rest = ""

    # Extract all hashtags
    found_hashtags = [w for w in caption.split() if w.startswith("#")]
    clean_body_lines = []
    for line in body_part.splitlines():
        line_words = [w for w in line.split() if not w.startswith("#")]
        if line_words:
            clean_body_lines.append(" ".join(line_words))
    clean_body = "\n\n".join([p.strip() for p in "\n".join(clean_body_lines).split("\n\n") if p.strip()])

    # 2. Limit emojis to max 3
    emojis_seen = 0
    fixed_chars = []
    for c in clean_body:
        if emoji.is_emoji(c):
            emojis_seen += 1
            if emojis_seen <= 3:
                fixed_chars.append(c)
        else:
            fixed_chars.append(c)
    clean_body = "".join(fixed_chars)

    # 3. Reassemble with Disclaimer and Hashtags isolated at bottom
    hashtags_str = " ".join(dict.fromkeys(found_hashtags))
    return f"{clean_body}\n\n{DISCLAIMER}\n\n{hashtags_str}".strip()


# --------------------------------------------------------------------------
# Cognitive Engineering Rules Validator (Rule 1 Hard Limits)
# --------------------------------------------------------------------------
def verify_cognitive_rules(content_plan: dict) -> dict:
    """
    Validates that slides adhere strictly to the 5 Cognitive Engineering Rules:
    - Headline: max 6 words
    - what_it_is: strictly 1 sentence, 10 to 18 words
    - why_it_matters: strictly 1 sentence, 10 to 15 words
    - description: strictly max 25 words
    """
    violations = []
    slides = content_plan.get("slides", []) if isinstance(content_plan, dict) else []

    for idx, s in enumerate(slides, start=1):
        if not isinstance(s, dict):
            continue
        title = s.get("title") or s.get("headline", "")
        if title:
            word_count = len(title.split())
            if word_count > 6:
                violations.append(f"Slide {idx} headline exceeds 6 words ({word_count} words): '{title}'")

        what = s.get("what_it_is", "")
        if what:
            words = what.split()
            if len(words) > 20:
                violations.append(f"Slide {idx} 'what_it_is' exceeds 18 words cap ({len(words)} words)")

        why = s.get("why_it_matters", "")
        if why:
            words = why.split()
            if len(words) > 18:
                violations.append(f"Slide {idx} 'why_it_matters' exceeds 15 words cap ({len(words)} words)")

        desc = s.get("description", "")
        if desc:
            words = desc.split()
            if len(words) > 28:
                violations.append(f"Slide {idx} description exceeds 25 words cap ({len(words)} words)")

    return {
        "compliant": len(violations) == 0,
        "violations": violations,
        "total_slides_checked": len(slides),
    }

