"""
core/competitor_analyzer.py
----------------------------
AI Virality Reverse-Engineering Analyzer for Competitor Instagram Posts:
1. Multi-Tier High-Precision LLM Engine:
   - Tier 1: OpenRouter (meta-llama/llama-3.3-70b-instruct / deepseek)
   - Tier 2: Groq (openai/gpt-oss-120b / llama-3.3-70b-versatile)
   - Tier 3: Hugging Face Serverless (Qwen/Qwen2.5-72B-Instruct)
   - Tier 4: Gemini 2.5 Flash (Reserve)
   - Tier 5: Resilient Fallback Heuristics
2. Deconstructs Hook Psychology, curiosity gaps, pattern interrupts, and trend angles.
3. Evaluates slide structure, visual density, and pacing.
4. Analyzes caption mechanics, line breaks, comment triggers, and save/share CTAs.
5. Computes quantitative Virality Score (1-100) and psychological drivers.
6. Generates the "Vmatrix Adaptation Blueprint" for 100% white-theme carousels.
"""

import os
import json
import requests
from typing import Dict, Any, Optional

from .utils import logger
from .config import config
from .db import db

VIRALITY_SCHEMA = {
    "type": "object",
    "properties": {
        "trend_angle": {"type": "string", "description": "The viral tech trend / architectural breakthrough being exploited."},
        "viral_hook": {"type": "string", "description": "The exact scroll-stopping pattern interrupt hook used in this post."},
        "hook_analysis": {
            "type": "object",
            "properties": {
                "hook_type": {"type": "string"},
                "hook_breakdown": {"type": "string"},
                "psychological_trigger": {"type": "string"},
            },
            "required": ["hook_type", "hook_breakdown", "psychological_trigger"],
        },
        "slide_pacing": {
            "type": "object",
            "properties": {
                "structure_type": {"type": "string"},
                "pacing_analysis": {"type": "string"},
                "educational_density": {"type": "string"},
            },
            "required": ["structure_type", "pacing_analysis", "educational_density"],
        },
        "caption_mechanics": {
            "type": "object",
            "properties": {
                "first_line_hook": {"type": "string"},
                "cta_effectiveness": {"type": "string"},
                "save_share_triggers": {"type": "string"},
                "hashtag_strategy": {"type": "string"},
                "suggested_caption": {"type": "string"},
            },
            "required": ["first_line_hook", "cta_effectiveness", "save_share_triggers", "hashtag_strategy"],
        },
        "virality_score": {"type": "integer", "minimum": 1, "maximum": 100},
        "why_it_went_viral": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 3,
            "maxItems": 4,
        },
        "vmatrix_blueprint": {
            "type": "object",
            "properties": {
                "adapted_title": {"type": "string"},
                "hook_line": {"type": "string"},
                "target_format": {"type": "string", "enum": ["listicle", "flow", "photo"]},
                "slide_ideas": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 5,
                    "maxItems": 5,
                },
                "competitive_advantage": {"type": "string"},
                "adapted_caption": {"type": "string"},
            },
            "required": ["adapted_title", "hook_line", "target_format", "slide_ideas", "competitive_advantage"],
        },
    },
    "required": [
        "trend_angle",
        "viral_hook",
        "hook_analysis",
        "slide_pacing",
        "caption_mechanics",
        "virality_score",
        "why_it_went_viral",
        "vmatrix_blueprint",
    ],
}

SYSTEM_PROMPT = """You are the Lead Growth Hacker, Viral Strategist, and Content Reverse-Engineer for @vmatrix.co.
Your mission is to deconstruct competitor Instagram posts in the Tech, AI, Coding, and Developer tools niche.

Analyze WHY this post achieved high reach/engagement and extract:
1. trend_angle: What macro tech trend or developer shift is this post riding?
2. viral_hook: What is the exact scroll-stopping pattern interrupt or curiosity hook?
3. hook_analysis: hook_type, hook_breakdown, psychological_trigger (FOMO, contrarian, status, secret knowledge).
4. slide_pacing: structure_type, pacing_analysis, educational_density.
5. caption_mechanics: first_line_hook, cta_effectiveness, save_share_triggers, hashtag_strategy, suggested_caption.
6. virality_score: 1-100 score based on virality mechanics and clarity.
7. why_it_went_viral: Exactly 3 punchy, specific psychological drivers.
8. vmatrix_blueprint ("Steal Like An Artist"):
   - adapted_title: Reframed for @vmatrix.co.
   - hook_line: Punchy 1-line hook for Slide 1.
   - target_format: 'listicle' (5-slide tools), 'flow' (architecture flowchart), or 'photo' (cheatsheet).
   - slide_ideas: Exactly 5 concrete slide points formatted for our 100% Pure White Retina theme.
   - competitive_advantage: How Vmatrix's version will be 10x higher quality than the competitor.
   - adapted_caption: Ready-to-use Instagram caption with hook, bullet points, and CTA.

You MUST output strictly valid JSON conforming to the schema.
"""


def _analyze_with_openrouter(user_prompt: str) -> Optional[Dict[str, Any]]:
    """Tier 1: High-precision virality breakdown via OpenRouter."""
    api_key = config.openrouter_api_key or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return None

    model = config.openrouter_model or os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://vmatrix.co",
        "X-Title": "Vmatrix Social OS",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": f"{SYSTEM_PROMPT}\nReturn strictly valid JSON."},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.25,
        "max_tokens": 2048,
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=28)
        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            start_idx = content.find("{")
            end_idx = content.rfind("}")
            if start_idx != -1 and end_idx != -1:
                content = content[start_idx : end_idx + 1]
            try:
                parsed = json.loads(content)
            except Exception:
                import re
                cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', ' ', content)
                parsed = json.loads(cleaned)
            logger.info("  ✓ AI Virality Analysis generated via OpenRouter (%s)", model)
            return parsed
        else:
            logger.warning("OpenRouter error (%d): %s", resp.status_code, resp.text[:180])
    except Exception as e:
        logger.warning("OpenRouter analysis request failed: %s", e)
    return None


def _get_groq_client():
    api_key = config.groq_api_key or os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        from groq import Groq
        return Groq(api_key=api_key)
    except Exception as e:
        logger.warning("Could not initialize Groq client: %s", e)
        return None


def _analyze_with_groq(user_prompt: str) -> Optional[Dict[str, Any]]:
    """Tier 2: Ultra-fast virality breakdown via Groq."""
    groq_client = _get_groq_client()
    if not groq_client:
        return None
    try:
        model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
        resp = groq_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": f"{SYSTEM_PROMPT}\nReturn strictly valid JSON."},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        parsed = json.loads(resp.choices[0].message.content)
        logger.info("  ✓ AI Virality Analysis generated via Groq (%s)", model)
        return parsed
    except Exception as e:
        logger.warning("Groq virality analysis error: %s", e)
    return None


def _analyze_with_huggingface(user_prompt: str) -> Optional[Dict[str, Any]]:
    """Tier 3: Serverless inference via Hugging Face InferenceClient (Qwen2.5-72B)."""
    token = config.huggingface_api_key or os.environ.get("HUGGINGFACE_API_KEY") or os.environ.get("HF_TOKEN")
    if not token:
        return None
    try:
        from huggingface_hub import InferenceClient
        client = InferenceClient(api_key=token)
        model = "Qwen/Qwen2.5-72B-Instruct"
        resp = client.chat_completion(
            messages=[
                {"role": "system", "content": f"{SYSTEM_PROMPT}\nReturn strictly valid JSON only."},
                {"role": "user", "content": user_prompt},
            ],
            model=model,
            max_tokens=1800,
            temperature=0.3,
        )
        content = resp.choices[0].message.content
        start_idx = content.find("{")
        end_idx = content.rfind("}")
        if start_idx != -1 and end_idx != -1:
            parsed = json.loads(content[start_idx : end_idx + 1])
            logger.info("  ✓ AI Virality Analysis generated via Hugging Face (%s)", model)
            return parsed
    except Exception as e:
        logger.warning("Hugging Face virality analysis error: %s", e)
    return None


def _fallback_analysis(post_data: Dict[str, Any]) -> Dict[str, Any]:
    caption = post_data.get("caption") or ""
    handle = post_data.get("handle") or "competitor"
    likes = post_data.get("likes") or 1000

    score = min(98, max(65, int(70 + (likes / 1000.0) * 2)))
    first_line = caption.split("\n")[0][:80] if caption else f"High engagement post by @{handle}"
    title_cand = first_line.replace("#", "").strip() or f"Top Tech Architecture by @{handle}"

    return {
        "trend_angle": "High-Utility Developer Efficiency & Automated AI Workflows",
        "viral_hook": first_line,
        "hook_analysis": {
            "hook_type": "Pattern Interrupt & Direct Value Promise",
            "hook_breakdown": f"Leverages immediate specificity: '{first_line}'. Creates a direct knowledge gap.",
            "psychological_trigger": "Fear of Missing Out (FOMO) & High-ROI Engineering Knowledge",
        },
        "slide_pacing": {
            "structure_type": "5-Stage Progressive Revelation",
            "pacing_analysis": "Starts with problem statement, delivers 3 actionable tools/steps, ends with high-value recap.",
            "educational_density": "High (actionable developer tips with minimal fluff)",
        },
        "caption_mechanics": {
            "first_line_hook": first_line,
            "cta_effectiveness": "Direct prompt asking users to bookmark/save for their next deployment.",
            "save_share_triggers": "High utility reference material engineered for bookmarks.",
            "hashtag_strategy": "Niche developer and AI hashtags for targeted algorithmic indexing.",
            "suggested_caption": f"⚡ {first_line}\n\nSave this guide for your next build. Bookmark for reference!\n\n#devcommunity #aiarchitecture #coding",
        },
        "virality_score": score,
        "why_it_went_viral": [
            "Solves an urgent, daily developer friction point with concrete code/tools.",
            "Visual structure makes complex technical architecture digestible in under 15 seconds.",
            "High saveability factor — followers save the post as a permanent reference guide.",
        ],
        "vmatrix_blueprint": {
            "adapted_title": f"Mastering {title_cand[:45]}",
            "hook_line": f"The Production Blueprint for {title_cand[:40]}",
            "target_format": "listicle",
            "slide_ideas": [
                f"Slide 1: Hook & Core Problem in {title_cand[:30]}",
                "Slide 2: Architectural Setup & Key Framework",
                "Slide 3: High-Performance Implementation Steps",
                "Slide 4: Production Pitfalls & Distroless Optimization",
                "Slide 5: Pro Recap & Saveable Cheatsheet",
            ],
            "competitive_advantage": "Clean 100% pure white aesthetic, verified code snippets, and zero visual clutter.",
            "adapted_caption": f"⚡ {title_cand[:50]}\n\nA production-ready breakdown for modern engineering teams.\n\nBookmark this for your next architecture review.\n\n#vmatrix #softwareengineering #coding",
        },
    }


def analyze_post_virality(post_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reverse-engineers why a competitor's post went viral using multi-tier AI:
    1. OpenRouter (Tier 1)
    2. Groq (Tier 2)
    3. Hugging Face (Tier 3)
    4. Gemini (Tier 4)
    5. Fallback Heuristics (Tier 5)
    """
    caption = post_data.get("caption") or ""
    handle = post_data.get("handle") or ""
    likes = post_data.get("likes") or 0
    comments = post_data.get("comments") or 0
    views = post_data.get("views") or 0
    shortcode = post_data.get("shortcode") or ""

    v_score = post_data.get("virality_score")
    is_outlier = post_data.get("is_outlier")
    raw_mult = post_data.get("raw_score")
    gate_3 = post_data.get("gate_3", {})
    er_pct = gate_3.get("er_percent")

    outlier_info = ""
    if is_outlier:
        mult_str = f"{raw_mult:.1f}x" if isinstance(raw_mult, (int, float)) else "2.0x+"
        v_str = f"{v_score:.1f}x" if isinstance(v_score, (int, float)) else "High"
        er_str = f"{er_pct:.2f}%" if isinstance(er_pct, (int, float)) else "Above Median"
        outlier_info = f"""
- 3-GATE OUTLIER STATUS: 🔥 CONFIRMED VIRAL OUTLIER
- Relative Outlier Multiplier: {mult_str} over account median
- Time-Decayed Virality Score: {v_str}
- Composite Weighted Engagement Rate: {er_str}
"""

    user_prompt = f"""
COMPETITOR POST TO REVERSE-ENGINEER:
- Creator Handle: @{handle}
- Likes: {likes:,}
- Comments: {comments:,}
- Views / Video Views: {views:,}{outlier_info}
- Caption:
\"\"\"{caption}\"\"\"
"""

    analysis = None

    # 1. Tier 1: OpenRouter (Deep Virality & Hook/Caption Intelligence)
    analysis = _analyze_with_openrouter(user_prompt)

    # 2. Tier 2: Groq (openai/gpt-oss-120b)
    if not analysis:
        analysis = _analyze_with_groq(user_prompt)

    # 3. Tier 3: Hugging Face (Qwen/Qwen2.5-72B)
    if not analysis:
        analysis = _analyze_with_huggingface(user_prompt)

    # 4. Tier 4: Gemini (if enabled)
    if not analysis and os.environ.get("ENABLE_GEMINI", "false").lower() in ("true", "1", "yes"):
        try:
            from google import genai
            from google.genai import types
            gemini_api_key = os.environ.get("GEMINI_API_KEY")
            if gemini_api_key:
                client = genai.Client(api_key=gemini_api_key)
                resp = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        response_mime_type="application/json",
                        response_schema=VIRALITY_SCHEMA,
                        temperature=0.3,
                    ),
                )
                analysis = json.loads(resp.text)
                logger.info("  ✓ AI Virality Analysis generated via Gemini 2.5 Flash")
        except Exception as e:
            logger.warning("Gemini virality analysis error: %s", e)

    # 5. Tier 5: Fallback Heuristics
    if not analysis:
        analysis = _fallback_analysis(post_data)

    # Normalize keys for bidirectional compatibility across models
    normalized = dict(analysis)
    if "hook_psychology" in analysis and "hook_analysis" not in analysis:
        normalized["hook_analysis"] = analysis["hook_psychology"]
    elif "hook_analysis" in analysis and "hook_psychology" not in analysis:
        normalized["hook_psychology"] = analysis["hook_analysis"]

    if "slide_pacing_structure" in analysis and "slide_pacing" not in analysis:
        normalized["slide_pacing"] = analysis["slide_pacing_structure"]
    elif "slide_pacing" in analysis and "slide_pacing_structure" not in analysis:
        normalized["slide_pacing_structure"] = analysis["slide_pacing"]

    if "vmatrix_adaptation_blueprint" in analysis and "vmatrix_blueprint" not in analysis:
        normalized["vmatrix_blueprint"] = analysis["vmatrix_adaptation_blueprint"]
    elif "vmatrix_blueprint" in analysis and "vmatrix_adaptation_blueprint" not in analysis:
        normalized["vmatrix_adaptation_blueprint"] = analysis["vmatrix_blueprint"]

    # Ensure virality_score is valid int between 1 and 100
    raw_v = normalized.get("virality_score") or normalized.get("score")
    if raw_v is None:
        likes = post_data.get("likes") or 1000
        normalized["virality_score"] = min(98, max(65, int(70 + (likes / 1000.0) * 2)))
    else:
        try:
            normalized["virality_score"] = min(100, max(1, int(float(raw_v))))
        except (ValueError, TypeError):
            normalized["virality_score"] = 85

    # Ensure trend_angle and viral_hook exist
    if not normalized.get("trend_angle"):
        normalized["trend_angle"] = "AI Engineering Architecture & Automated Developer Tools"
    if not normalized.get("viral_hook"):
        normalized["viral_hook"] = caption.split("\n")[0][:80] if caption else "Why top engineering teams are changing workflows"

    # Ensure nested objects are dicts
    if isinstance(normalized.get("hook_analysis"), str):
        normalized["hook_analysis"] = {
            "hook_type": "Pattern Interrupt",
            "hook_breakdown": normalized["hook_analysis"],
            "psychological_trigger": "Curiosity Gap & High Value",
        }
    if isinstance(normalized.get("slide_pacing"), str):
        normalized["slide_pacing"] = {
            "structure_type": "Progressive Revelation",
            "pacing_analysis": normalized["slide_pacing"],
            "educational_density": "High",
        }
    if isinstance(normalized.get("caption_mechanics"), str):
        normalized["caption_mechanics"] = {
            "first_line_hook": caption[:60] if caption else "N/A",
            "cta_effectiveness": normalized["caption_mechanics"],
            "save_share_triggers": "Direct reference bookmark trigger",
            "hashtag_strategy": "Niche audience indexing",
            "suggested_caption": caption[:120] if caption else "",
        }
    if isinstance(normalized.get("vmatrix_blueprint"), str):
        normalized["vmatrix_blueprint"] = {
            "adapted_title": f"Mastering {caption[:35] if caption else 'Architecture'}",
            "hook_line": f"The Essential Guide to {caption[:30] if caption else 'Production'}",
            "target_format": "listicle",
            "slide_ideas": ["Overview", "Core Setup", "Implementation", "Pitfalls", "Summary"],
            "competitive_advantage": normalized["vmatrix_blueprint"],
            "adapted_caption": f"⚡ Production Blueprint\n\nBookmark for reference.\n\n#coding #tech",
        }

    analysis = normalized

    # Update database record with analysis
    if shortcode:
        db.update_virality_analysis(shortcode, analysis)

    return analysis
