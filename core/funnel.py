"""
core/funnel.py
--------------
5-Stage Filtering Funnel for Content & Topic Discovery:
Turns 100+ raw, noisy headlines from Google Trends, RSS feeds, and developer APIs
into top-performing, viral, educational post topics.

Stages:
  1. 🔴 Stage 1: Fast Keyword Blacklist (Throw out junk / $0, 0ms)
  2. 🟢 Stage 2: Positive Niche Scoring (Rule-based / $0, 1ms)
  3. 🧠 Stage 3: Semantic LLM Classifier (Gemini 2.5 Flash / <$0.0001, ~0.5s)
  4. 🔄 Stage 4: Vector Anti-Duplication (Cosine Similarity vs 30-Day Memory)
  5. 🏆 Stage 5: Format Fit & Actionability Score (3-5 Concrete Steps Ready)
"""

import os
import re
import json
from typing import List, Dict, Any, Tuple, Optional

from google import genai
from google.genai import types

from .utils import retry_with_backoff, logger
from .memory import check_max_similarity, record_post



# ==============================================================================
# 🔴 STAGE 1: Fast Keyword Blacklist (Regex / Cost: $0, 0ms)
# ==============================================================================

EXCLUDED_WORDS = {
    # Sports
    "football", "cricket", "soccer", "ipl", "premier league", "nfl", "nba",
    "fifa", "wimbledon", "olympics", "badminton", "tennis", "kabaddi", "match",
    "vs", "score", "stadium", "tournament", "championship", "goal", "wicket",
    "messi", "ronaldo", "virat kohli", "rohit sharma", "super bowl",

    # Entertainment, Celebrity & Pop Culture
    "movie", "actor", "actress", "trailer", "box office", "hollywood", "bollywood",
    "cinema", "celebrity", "song", "album", "grammy", "oscar", "emmy", "concert",
    "singer", "tv show", "episode", "season", "netflix series", "gossip",
    "dating", "divorce", "wedding", "kardashian", "taylor swift", "bigg boss",

    # Politics, Crime & Scandals
    "election", "ballot", "vote", "poll", "minister", "bjp", "congress", "democrat",
    "republican", "scandal", "murder", "arrest", "arrested", "police", "court case",
    "sentenced", "protest", "riot", "war", "shooting", "assault", "rape", "jail",

    # Lifestyle, Trivia & Misc Off-topic
    "recipe", "horoscope", "astrology", "zodiac", "weather", "earthquake", "flood",
    "cyclone", "fashion", "beauty", "makeup", "diet", "weight loss", "lottery",
}


def passes_blacklist(title: str) -> bool:
    """
    Stage 1 Filter: Returns False if title contains any blacklisted junk word.
    Uses whole-word and phrase matching for speed and precision.
    """
    clean = title.lower().strip()
    words_in_title = set(re.findall(r"\b[a-z0-9\'-]+\b", clean))

    for junk in EXCLUDED_WORDS:
        if " " in junk:
            if junk in clean:
                return False
        else:
            if junk in words_in_title:
                return False
    return True


def apply_stage1_blacklist(items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Filters raw items through Stage 1 Blacklist.
    Returns: (passed_items, dropped_items)
    """
    passed = []
    dropped = []
    for item in items:
        title = item.get("title", "")
        if passes_blacklist(title):
            passed.append(item)
        else:
            dropped_item = dict(item)
            dropped_item["drop_reason"] = "Stage 1: Contains blacklisted off-topic keyword"
            dropped.append(dropped_item)
    return passed, dropped


# ==============================================================================
# 🟢 STAGE 2: Positive Niche Scoring (Rule-based / Cost: $0, 1ms)
# ==============================================================================

TECH_KEYWORDS = {
    # AI & ML
    "ai": 3, "llm": 4, "gpt": 3, "claude": 4, "gemini": 4, "deepseek": 4, "mistral": 3,
    "llama": 3, "openai": 4, "anthropic": 4, "agent": 3, "agents": 3, "prompt": 3,
    "prompts": 3, "rag": 4, "machine learning": 3, "deep learning": 3, "neural": 2,
    "gpu": 3, "cuda": 3, "pytorch": 3, "tensorflow": 3, "transformer": 3, "embeddings": 3,
    "multimodal": 3, "fine-tuning": 4, "distill": 3, "reasoning": 3,

    # Coding & Developer Tools
    "python": 3, "javascript": 2, "typescript": 3, "react": 3, "rust": 3, "golang": 3,
    "git": 4, "github": 4, "docker": 4, "kubernetes": 3, "cursor": 4, "vscode": 3,
    "copilot": 3, "api": 2, "apis": 2, "database": 2, "postgres": 3, "sql": 2,
    "vector": 3, "frontend": 2, "backend": 2, "devops": 3, "open-source": 3,
    "framework": 2, "library": 2, "fastapi": 4, "streamlit": 4, "terminal": 3, "cli": 3,
    "webdev": 3, "coding": 3, "developer": 2, "software": 2, "sdk": 3, "npm": 3, "pip": 3,
}

FINANCE_KEYWORDS = {
    "invest": 4, "investing": 4, "stocks": 4, "stock market": 4, "s&p 500": 5,
    "index fund": 5, "etf": 4, "compound interest": 5, "fintech": 3, "wealth": 4,
    "portfolio": 4, "dividend": 4, "crypto": 3, "bitcoin": 3, "ethereum": 3,
    "passive income": 5, "valuation": 3, "ipo": 3, "seed round": 4, "venture capital": 4,
    "fundraising": 3, "savings": 3, "net worth": 4, "personal finance": 5, "nasdaq": 3,
}


def compute_niche_score(text: str) -> Tuple[int, str]:
    """
    Calculates positive niche relevancy score and dominant category.
    Returns: (score, primary_category)
    """
    clean = text.lower()
    words_in_text = set(re.findall(r"\b[a-z0-9\'-]+\b", clean))

    tech_score = 0
    for kw, weight in TECH_KEYWORDS.items():
        if " " in kw:
            if kw in clean:
                tech_score += weight
        elif kw in words_in_text:
            tech_score += weight

    fin_score = 0
    for kw, weight in FINANCE_KEYWORDS.items():
        if " " in kw:
            if kw in clean:
                fin_score += weight
        elif kw in words_in_text:
            fin_score += weight

    total_score = tech_score + fin_score
    if total_score == 0:
        return 0, "OTHER"

    if tech_score >= fin_score:
        category = "AI & CODING" if tech_score > 0 else "TOOLS"
    else:
        category = "FINANCE"

    return total_score, category


def apply_stage2_niche_scoring(
    items: List[Dict[str, Any]],
    min_score: int = 2,
    top_k: int = 15,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Stage 2 Filter: Scores candidates based on niche keyword density,
    ranks by score, and keeps the top_k relevant items.
    """
    scored = []
    dropped = []

    for item in items:
        text = f"{item.get('title', '')} {item.get('summary', '')}"
        score, category = compute_niche_score(text)
        item_copy = dict(item)
        item_copy["niche_score"] = score
        item_copy["category"] = category

        if score >= min_score:
            scored.append(item_copy)
        else:
            item_copy["drop_reason"] = f"Stage 2: Low niche score ({score} < {min_score})"
            dropped.append(item_copy)

    # Sort descending by score
    scored.sort(key=lambda x: x["niche_score"], reverse=True)
    passed = scored[:top_k]
    dropped.extend(scored[top_k:])

    return passed, dropped


# ==============================================================================
# 🧠 STAGE 3: Semantic LLM Classifier (Gemini 2.5 Flash / Cost: <$0.0001, 0.5s)
# ==============================================================================

_CLASSIFIER_SCHEMA = {
    "type": "object",
    "properties": {
        "classifications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "original_title": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": ["PURE_AI", "PURE_FINANCE", "MIXED", "OFF_TOPIC"],
                    },
                    "is_educational": {"type": "boolean"},
                    "refined_title": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["original_title", "category", "is_educational", "refined_title"],
            },
        }
    },
    "required": ["classifications"],
}

_CLASSIFIER_SYSTEM_PROMPT = """You are a senior social media curator for a premier educational channel.
You filter raw tech & financial trends to eliminate false positives and non-educational noise.

For each headline:
1. Classify category into:
   - PURE_AI: AI models, LLMs, prompt engineering, AI agents, generative tech.
   - PURE_FINANCE: Investing, wealth building, index funds, compound interest, personal finance.
   - MIXED: Developer tools, coding libraries, fintech, open-source software, productivity tech.
   - OFF_TOPIC: Entertainment, sports, generic corporate drama, gossip, politics, off-topic.
2. Set is_educational: true only if the topic can teach a developer/investor useful tips, tools, or concepts.
3. Provide refined_title: a clean, punchy headline without clickbait or reporter names.
"""


def _fallback_semantic_classify(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Heuristic fallback when Gemini is unavailable."""
    results = []
    for it in items:
        cat = it.get("category", "AI & CODING")
        if cat == "FINANCE":
            assigned = "PURE_FINANCE"
        elif "AI" in cat:
            assigned = "PURE_AI"
        else:
            assigned = "MIXED"

        results.append({
            "original_title": it["title"],
            "category": assigned,
            "is_educational": True,
            "refined_title": it["title"],
            "reason": "Passed heuristic keyword validation",
        })
    return results


@retry_with_backoff(max_attempts=2, base_delay=1.0, exceptions=(Exception,))
def _call_gemini_classifier(client: genai.Client, titles: List[str]) -> List[Dict[str, Any]]:
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"HEADLINES TO CLASSIFY:\n{json.dumps(titles, indent=2)}",
        config=types.GenerateContentConfig(
            system_instruction=_CLASSIFIER_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=_CLASSIFIER_SCHEMA,
            temperature=0.2,
        ),
    )
    parsed = json.loads(resp.text)
    return parsed.get("classifications", [])


def apply_stage3_semantic_classifier(items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Stage 3 Filter: Batched semantic LLM classification to filter false positives
    and reject OFF_TOPIC / non-educational trends.
    """
    if not items:
        return [], []

    titles = [it["title"] for it in items]
    api_key = os.environ.get("GEMINI_API_KEY")

    classifications = []
    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            classifications = _call_gemini_classifier(client, titles)
        except Exception as e:
            logger.warning("Stage 3 Gemini Classifier error, falling back to heuristics: %s", e)
            classifications = _fallback_semantic_classify(items)
    else:
        classifications = _fallback_semantic_classify(items)

    class_map = {c.get("original_title", ""): c for c in classifications}

    passed = []
    dropped = []

    for item in items:
        title = item.get("title", "")
        c_info = class_map.get(title)

        if not c_info:
            # Fallback match by start of title
            for k, v in class_map.items():
                if k and (k in title or title in k):
                    c_info = v
                    break

        item_copy = dict(item)
        if c_info:
            category = c_info.get("category", "MIXED")
            is_edu = c_info.get("is_educational", True)
            refined = c_info.get("refined_title") or title

            item_copy["semantic_category"] = category
            item_copy["refined_title"] = refined

            if category != "OFF_TOPIC" and is_edu:
                passed.append(item_copy)
            else:
                item_copy["drop_reason"] = f"Stage 3: Classified as {category} (is_educational={is_edu})"
                dropped.append(item_copy)
        else:
            passed.append(item_copy)

    return passed, dropped


# ==============================================================================
# 🔄 STAGE 4: Vector Anti-Duplication (Cosine Similarity / Cost: <$0.0001)
# ==============================================================================

def apply_stage4_vector_deduplication(
    items: List[Dict[str, Any]],
    similarity_threshold: float = 0.80,
    history_days: int = 30,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Stage 4 Filter: Compares candidate embeddings against past 30 days of posts.
    Drops anything with Cosine Similarity > threshold (0.80).
    """
    passed = []
    dropped = []

    for item in items:
        title = item.get("refined_title") or item.get("title", "")
        max_sim, matched_title = check_max_similarity(title, days=history_days)

        item_copy = dict(item)
        item_copy["max_history_similarity"] = round(max_sim, 3)
        item_copy["matched_past_post"] = matched_title

        if max_sim > similarity_threshold:
            item_copy["drop_reason"] = (
                f"Stage 4: Duplicate of recent post ({max_sim:.2f} > {similarity_threshold}) — '{matched_title}'"
            )
            dropped.append(item_copy)
        else:
            passed.append(item_copy)

    return passed, dropped


# ==============================================================================
# 🏆 STAGE 5: Format Fit & Actionability Score
# ==============================================================================

_ACTIONABILITY_SCHEMA = {
    "type": "object",
    "properties": {
        "evaluations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "actionability_score": {"type": "integer", "minimum": 1, "maximum": 10},
                    "hook_angle": {"type": "string"},
                    "step_ideas": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 3,
                        "maxItems": 5,
                    },
                    "is_winning_candidate": {"type": "boolean"},
                },
                "required": ["title", "actionability_score", "hook_angle", "step_ideas", "is_winning_candidate"],
            },
        }
    },
    "required": ["evaluations"],
}

_ACTIONABILITY_SYSTEM_PROMPT = """You are the Lead Content Director for Instagram educational carousels.
Evaluate candidates for 'Educational Format Fit' (can we build 3-5 concrete steps/slides from this?).

Examples:
- "OpenAI CEO gets salary update" -> Actionability 2/10 (News gossip, no concrete steps)
- "DeepSeek releases V3.2 with FP8 Support" -> Actionability 9/10 (Can teach 4 concrete features & how to use them)
- "5 Cursor AI Tricks for Fast Debugging" -> Actionability 10/10 (Direct tutorial steps)

For each topic, return:
- actionability_score (1 to 10)
- hook_angle (punchy 1-line hook for slide 1)
- step_ideas (3-5 concrete steps/tools for slides 2-4)
- is_winning_candidate: true if actionability_score >= 7.
"""


def _fallback_actionability(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results = []
    for it in items:
        title = it.get("refined_title") or it.get("title", "")
        results.append({
            "title": title,
            "actionability_score": 8,
            "hook_angle": f"The Essential Guide to {title}",
            "step_ideas": ["Overview & Setup", "Core Mechanism & Features", "Practical Use Case", "Pro Tips & Summary"],
            "is_winning_candidate": True,
        })
    return results


@retry_with_backoff(max_attempts=2, base_delay=1.0, exceptions=(Exception,))
def _call_gemini_actionability(client: genai.Client, topics: List[str]) -> List[Dict[str, Any]]:
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"TOPICS TO EVALUATE:\n{json.dumps(topics, indent=2)}",
        config=types.GenerateContentConfig(
            system_instruction=_ACTIONABILITY_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=_ACTIONABILITY_SCHEMA,
            temperature=0.3,
        ),
    )
    parsed = json.loads(resp.text)
    return parsed.get("evaluations", [])


def apply_stage5_actionability_scoring(
    items: List[Dict[str, Any]],
    min_score: int = 7,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Stage 5 Filter: Assesses educational format fit and step actionability (1-10).
    Returns ranked winning post topics ready for immediate carousel generation.
    """
    if not items:
        return [], []

    titles = [it.get("refined_title") or it.get("title", "") for it in items]
    api_key = os.environ.get("GEMINI_API_KEY")

    evals = []
    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            evals = _call_gemini_actionability(client, titles)
        except Exception as e:
            logger.warning("Stage 5 Actionability error, falling back: %s", e)
            evals = _fallback_actionability(items)
    else:
        evals = _fallback_actionability(items)

    eval_map = {e.get("title", ""): e for e in evals}

    passed = []
    dropped = []

    for item in items:
        title = item.get("refined_title") or item.get("title", "")
        e_info = eval_map.get(title)

        if not e_info:
            for k, v in eval_map.items():
                if k and (k in title or title in k):
                    e_info = v
                    break

        item_copy = dict(item)
        if e_info:
            score = e_info.get("actionability_score", 7)
            hook = e_info.get("hook_angle", "")
            steps = e_info.get("step_ideas", [])
            is_winner = e_info.get("is_winning_candidate", score >= min_score)

            item_copy["actionability_score"] = score
            item_copy["hook_angle"] = hook
            item_copy["step_ideas"] = steps

            if is_winner or score >= min_score:
                passed.append(item_copy)
            else:
                item_copy["drop_reason"] = f"Stage 5: Low actionability score ({score}/10 — lacks 3-5 concrete steps)"
                dropped.append(item_copy)
        else:
            item_copy["actionability_score"] = 8
            item_copy["hook_angle"] = f"How to master {title}"
            item_copy["step_ideas"] = ["Getting Started", "Key Method", "Pro Application"]
            passed.append(item_copy)

    # Sort winners by actionability score
    passed.sort(key=lambda x: x.get("actionability_score", 0), reverse=True)
    return passed, dropped


# ==============================================================================
# 🚀 Full 5-Stage Funnel Orchestrator
# ==============================================================================

def run_filtering_funnel(raw_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Executes all 5 stages of the filtering funnel on raw gathered data:
      Raw (100+) -> Stage 1 Blacklist -> Stage 2 Niche -> Stage 3 Semantic -> Stage 4 Dedup -> Stage 5 Actionability -> Winning Topics
    Returns complete funnel report with drop-off statistics and ranked winners.
    """
    initial_count = len(raw_items)

    # Stage 1: Fast Blacklist
    s1_passed, s1_dropped = apply_stage1_blacklist(raw_items)

    # Stage 2: Positive Niche Scoring
    s2_passed, s2_dropped = apply_stage2_niche_scoring(s1_passed, min_score=2, top_k=15)

    # Stage 3: Semantic LLM Classifier
    s3_passed, s3_dropped = apply_stage3_semantic_classifier(s2_passed)

    # Stage 4: Vector Anti-Duplication
    s4_passed, s4_dropped = apply_stage4_vector_deduplication(s3_passed, similarity_threshold=0.80)

    # Stage 5: Format Fit & Actionability
    s5_passed, s5_dropped = apply_stage5_actionability_scoring(s4_passed, min_score=7)

    # If Stage 5 pruned everything, fall back gracefully to s4_passed
    winners = s5_passed if s5_passed else s4_passed[:3]

    return {
        "raw_count": initial_count,
        "stage_counts": {
            "raw": initial_count,
            "stage1_blacklist": len(s1_passed),
            "stage2_niche": len(s2_passed),
            "stage3_semantic": len(s3_passed),
            "stage4_dedup": len(s4_passed),
            "stage5_actionable": len(winners),
        },
        "stage_drops": {
            "stage1": s1_dropped,
            "stage2": s2_dropped,
            "stage3": s3_dropped,
            "stage4": s4_dropped,
            "stage5": s5_dropped,
        },
        "winning_topics": winners,
    }
