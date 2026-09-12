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
    "Your audience consists of analytically curious developers, tech enthusiasts, researchers, and students. "
    "Followers expect sharp, highly specific, technical insights. "
    "Avoid generic AI clichés (e.g., 'dive deep', 'game-changer', 'revolutionizing the world'). "
    "Focus on concrete utility, workflow shortcuts, latency metrics, or code mechanics. "
    "Default tone: confident, precise, beginner-friendly yet technically sound."
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
