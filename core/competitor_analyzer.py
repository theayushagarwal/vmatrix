"""
core/competitor_analyzer.py
----------------------------
AI Virality Reverse-Engineering Analyzer for Competitor Instagram Posts:
1. Deconstructs Hook Psychology, curiosity gaps, and pattern interrupts.
2. Evaluates slide structure, pacing, and visual information density.
3. Analyzes caption mechanics, line breaks, and save/share Call-To-Action (CTA).
4. Computes quantitative Virality Score (1-100) and psychological drivers.
5. Generates the "Vmatrix Adaptation Blueprint" for 100% white-theme carousels.
"""

import os
import json
from typing import Dict, Any, Optional
from google import genai
from google.genai import types

from .utils import logger, retry_with_backoff
from .db import db

VIRALITY_SCHEMA = {
    "type": "object",
    "properties": {
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
            },
            "required": ["adapted_title", "hook_line", "target_format", "slide_ideas", "competitive_advantage"],
        },
    },
    "required": [
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

Analyze WHY this post achieved high reach/engagement:
1. Hook Psychology: What was the exact pattern interrupt or curiosity gap that made users stop scrolling?
2. Slide Pacing & Structure: How is the value delivered? (Comparison, Cheat Sheet, Code Steps, Architectural Blueprint).
3. Caption Mechanics: How the caption drives Saves, Shares, and Comments.
4. Virality Score (1-100): Calculated score based on engagement metrics, clarity, and utility.
5. Why It Went Viral: 3 punchy, specific psychological drivers.
6. Vmatrix Adaptation Blueprint ("Steal Like An Artist"):
   - adapted_title: Reframed for our high-end engineering brand @vmatrix.co.
   - hook_line: Punchy 1-line hook for Slide 1.
   - target_format: 'listicle' (5-slide tools), 'flow' (architecture flowchart), or 'photo' (cheatsheet).
   - slide_ideas: Exactly 5 concrete slide points formatted for our 100% Pure White Retina theme.
   - competitive_advantage: How Vmatrix's version will be 10x higher quality than the competitor's post.

You MUST output strictly valid JSON conforming to the schema.
"""


def _get_groq_client():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        from groq import Groq
        return Groq(api_key=api_key)
    except Exception as e:
        logger.warning("Could not initialize Groq client: %s", e)
        return None


def _fallback_analysis(post_data: Dict[str, Any]) -> Dict[str, Any]:
    caption = post_data.get("caption") or ""
    handle = post_data.get("handle") or "competitor"
    likes = post_data.get("likes") or 1000

    # Calculate fallback score
    score = min(98, max(65, int(70 + (likes / 1000.0) * 2)))

    first_line = caption.split("\n")[0][:80] if caption else f"High engagement post by @{handle}"
    title_cand = first_line.replace("#", "").strip() or f"Top Tech Architecture by @{handle}"

    return {
        "hook_analysis": {
            "hook_type": "Pattern Interrupt & Value Promise",
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
        },
    }


def analyze_post_virality(post_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reverse-engineers why a competitor's post went viral.
    Returns structured analysis with Hook Breakdown, Virality Score, and Vmatrix Adaptation Blueprint.
    Automatically saves the result back into Supabase and local DB.
    """
    caption = post_data.get("caption") or ""
    handle = post_data.get("handle") or ""
    likes = post_data.get("likes") or 0
    comments = post_data.get("comments") or 0
    views = post_data.get("views") or 0
    shortcode = post_data.get("shortcode") or ""

    user_prompt = f"""
COMPETITOR POST TO REVERSE-ENGINEER:
- Creator Handle: @{handle}
- Likes: {likes:,}
- Comments: {comments:,}
- Views / Video Views: {views:,}
- Caption:
\"\"\"{caption}\"\"\"
"""

    analysis = None

    # 1. Primary: Groq (openai/gpt-oss-120b)
    groq_client = _get_groq_client()
    if groq_client:
        try:
            model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
            resp = groq_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": f"{SYSTEM_PROMPT}\nReturn strictly valid JSON conforming to the requested schema."},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            analysis = json.loads(resp.choices[0].message.content)
            logger.info("  ✓ AI Virality Analysis generated via Groq (%s)", model)
        except Exception as e:
            logger.warning("Groq virality analysis error: %s", e)

    # 2. Secondary: Gemini (if Groq failed and Gemini is available)
    if not analysis and os.environ.get("ENABLE_GEMINI", "false").lower() in ("true", "1", "yes"):
        gemini_api_key = os.environ.get("GEMINI_API_KEY")
        if gemini_api_key:
            try:
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

    # 3. Fallback Heuristics
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
        }
    if isinstance(normalized.get("vmatrix_blueprint"), str):
        normalized["vmatrix_blueprint"] = {
            "adapted_title": f"Mastering {caption[:35] if caption else 'Architecture'}",
            "hook_line": f"The Essential Guide to {caption[:30] if caption else 'Production'}",
            "target_format": "listicle",
            "slide_ideas": ["Overview", "Core Setup", "Implementation", "Pitfalls", "Summary"],
            "competitive_advantage": normalized["vmatrix_blueprint"],
        }

    analysis = normalized

    # Update database record with analysis
    if shortcode:
        db.update_virality_analysis(shortcode, analysis)

    return analysis
