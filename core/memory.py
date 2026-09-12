"""
core/memory.py
--------------
Persistent post history and vector embedding memory.
Stores the last 30+ days of published / generated topics and embeddings to
power Stage 4 (Vector Anti-Duplication with Cosine Similarity).
"""

import os
import json
import math
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from google import genai
from .utils import logger
from .database import sync_post_to_supabase, fetch_top_performing_posts_from_supabase

MEMORY_FILE_PATH = Path(__file__).resolve().parent.parent / "data" / "post_history.json"


def _get_embedding_client() -> Optional[genai.Client]:
    if os.environ.get("ENABLE_GEMINI", "false").lower() not in ("true", "1", "yes"):
        return None
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception as e:
        logger.warning("Could not initialize Gemini Client for embeddings: %s", e)
        return None


def compute_fallback_embedding(text: str, dim: int = 128) -> List[float]:
    """
    Deterministic n-gram character hashing vector fallback when offline or without API key.
    Provides reliable cosine similarity for deduplication without external API calls.
    """
    text_clean = text.lower().strip()
    vector = [0.0] * dim
    if not text_clean:
        return vector

    # Character tri-grams
    words = text_clean.split()
    for word in words:
        for i in range(len(word) - 2):
            trigram = word[i : i + 3]
            idx = hash(trigram) % dim
            vector[idx] += 1.0

    # Word unigrams
    for word in words:
        idx = hash(word) % dim
        vector[idx] += 2.0

    # L2 Normalize
    norm = math.sqrt(sum(x * x for x in vector))
    if norm > 0:
        vector = [x / norm for x in vector]
    return vector


def get_text_embedding(text: str) -> List[float]:
    """
    Generates a 768-dimension embedding using Gemini text-embedding-004.
    Falls back to deterministic character vector if API key is not configured.
    """
    client = _get_embedding_client()
    if client:
        try:
            resp = client.models.embed_content(
                model="text-embedding-004",
                contents=text,
            )
            # Response from google.genai has .embedding.values or .embeddings[0].values
            if hasattr(resp, "embedding") and hasattr(resp.embedding, "values"):
                return list(resp.embedding.values)
            elif hasattr(resp, "embeddings") and resp.embeddings:
                return list(resp.embeddings[0].values)
        except Exception as e:
            logger.warning("Gemini text-embedding-004 error, using fallback vector: %s", e)

    return compute_fallback_embedding(text)


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Computes the cosine similarity between two vector lists."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


def load_post_history() -> List[Dict[str, Any]]:
    """Loads all post history items from data/post_history.json."""
    if not MEMORY_FILE_PATH.exists() or MEMORY_FILE_PATH.stat().st_size == 0:
        return []
    try:
        with open(MEMORY_FILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Error reading post history from %s: %s", MEMORY_FILE_PATH, e)
        return []


def save_post_history(history: List[Dict[str, Any]]) -> None:
    """Saves post history items to data/post_history.json."""
    MEMORY_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(MEMORY_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("Error saving post history to %s: %s", MEMORY_FILE_PATH, e)


def get_recent_posts(days: int = 30) -> List[Dict[str, Any]]:
    """Retrieves posts published within the last N days."""
    history = load_post_history()
    cutoff = time.time() - (days * 86400)
    return [item for item in history if item.get("timestamp", 0) >= cutoff]


def record_post(
    title: str,
    category: str = "AI & CODING",
    hook: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    post_id: Optional[str] = None,
    format_type: Optional[str] = None,
    slide_urls: Optional[List[str]] = None,
    caption: Optional[str] = None,
    auto_comment: Optional[str] = None,
    insights: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Records a new published/chosen topic, slide URLs, and vector embedding into history memory.
    Synchronizes complete payload to Supabase PostgreSQL table 'posts'.
    """
    history = load_post_history()
    embedding = get_text_embedding(title)

    meta = dict(metadata or {})
    if post_id:
        meta["post_id"] = post_id
    if format_type:
        meta["format"] = format_type
    if slide_urls:
        meta["slide_urls"] = slide_urls
    if caption:
        meta["caption"] = caption
    if auto_comment:
        meta["auto_comment"] = auto_comment
    if insights:
        meta["insights"] = insights

    # Check if this topic already exists in history to update or prepend
    existing_idx = None
    for idx, item in enumerate(history):
        if item.get("title") == title:
            existing_idx = idx
            break

    entry = {
        "title": title,
        "category": category,
        "hook": hook,
        "timestamp": time.time(),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "embedding": embedding,
        "post_id": post_id,
        "format": format_type,
        "slide_urls": slide_urls,
        "caption": caption,
        "auto_comment": auto_comment,
        "insights": insights,
        "metadata": meta,
    }

    if existing_idx is not None:
        # Preserve earlier metrics if not overwritten
        old_insights = history[existing_idx].get("insights")
        if old_insights and not insights:
            entry["insights"] = old_insights
            meta["insights"] = old_insights
        history[existing_idx] = entry
    else:
        history.insert(0, entry)

    history = history[:200]
    save_post_history(history)

    # Sync to Supabase in cloud if connected
    sync_post_to_supabase(
        title=title,
        category=category,
        hook=hook,
        embedding=embedding,
        metadata=meta,
        post_id=post_id,
        format_type=format_type,
        slide_urls=slide_urls,
        caption=caption,
        auto_comment=auto_comment,
        insights=insights,
    )

    return entry


def get_top_performing_topics(min_score: float = 20.0, limit: int = 15) -> List[Dict[str, Any]]:
    """
    Retrieves historical top-performing topics combining Supabase cloud records
    and local post history.
    Used by the 5-Stage Funnel feedback loop to calculate resonance boosts.
    """
    winners_by_title: Dict[str, Dict[str, Any]] = {}

    # 1. Fetch from Supabase
    try:
        supabase_winners = fetch_top_performing_posts_from_supabase(min_engagement_score=min_score, limit=limit * 2)
        for sw in supabase_winners:
            title = sw.get("title")
            if title:
                winners_by_title[title] = sw
    except Exception as e:
        logger.debug("Could not fetch top performers from Supabase: %s", e)

    # 2. Augment from local history
    history = load_post_history()
    for item in history:
        title = item.get("title")
        if not title:
            continue
        insights = item.get("insights") or {}
        score = item.get("engagement_score") or insights.get("engagement_score", 0.0)
        if score >= min_score:
            if title not in winners_by_title or score > winners_by_title[title].get("engagement_score", 0.0):
                winners_by_title[title] = {
                    "title": title,
                    "category": item.get("category", "AI & CODING"),
                    "engagement_score": score,
                    "saved": insights.get("saved", 0),
                    "shares": insights.get("shares", 0),
                    "reach": insights.get("reach", 0),
                    "embedding": item.get("embedding"),
                }

    ranked = sorted(winners_by_title.values(), key=lambda x: x.get("engagement_score", 0.0), reverse=True)
    return ranked[:limit]


def calculate_topic_resonance_boost(candidate_title: str) -> float:
    """
    Computes a historical resonance bonus (0.0 to +3.0 points) for a candidate topic.
    If the candidate is semantically similar (cosine similarity >= 0.65) to past
    high-engagement posts, it earns a boost to bias Stage 5 ranking toward proven winners.
    """
    top_topics = get_top_performing_topics(min_score=20.0, limit=15)
    if not top_topics:
        return 0.0

    cand_vec = get_text_embedding(candidate_title)
    max_sim = 0.0
    matched_winner = None

    for winner in top_topics:
        win_vec = winner.get("embedding")
        if not win_vec:
            # Generate on the fly if missing
            win_vec = get_text_embedding(winner.get("title", ""))
            winner["embedding"] = win_vec

        sim = cosine_similarity(cand_vec, win_vec)
        if sim > max_sim:
            max_sim = sim
            matched_winner = winner

    # Resonance boost threshold: >= 0.65 similarity with a past winning post
    if max_sim >= 0.65 and matched_winner:
        score = matched_winner.get("engagement_score", 20.0)
        # Scaled bonus: up to +3.0 based on similarity and engagement
        base_boost = (max_sim - 0.60) * 10.0  # e.g., 0.70 -> 1.0, 0.85 -> 2.5
        score_multiplier = min(1.3, max(1.0, score / 50.0))
        boost = round(min(3.0, max(0.5, base_boost * score_multiplier)), 1)
        logger.info(
            "  ⚡ Historical Resonance Boost: '+%.1f' for '%s' (matched past winner '%s' with sim=%.2f, engagement=%.1f)",
            boost, candidate_title, matched_winner.get("title"), max_sim, score
        )
        return boost

    return 0.0


def check_max_similarity(candidate_title: str, days: int = 30) -> tuple[float, Optional[str]]:
    """
    Compares candidate title embedding against posts in the last N days.
    Returns: (max_similarity_score, matching_recent_title)
    """
    recent = get_recent_posts(days=days)
    if not recent:
        return 0.0, None

    cand_vec = get_text_embedding(candidate_title)
    max_sim = 0.0
    matched_title = None

    for item in recent:
        item_vec = item.get("embedding")
        if not item_vec:
            continue
        sim = cosine_similarity(cand_vec, item_vec)
        if sim > max_sim:
            max_sim = sim
            matched_title = item.get("title")

    return max_sim, matched_title


def get_time_since_last_post() -> Optional[float]:
    """
    Returns the hours elapsed since the most recent post was recorded,
    or None if no post exists in history.
    """
    history = load_post_history()
    if not history:
        return None
    last_ts = history[0].get("timestamp", 0)
    if not last_ts:
        return None
    return max(0.0, (time.time() - last_ts) / 3600.0)


def check_duplicate_guardrails(
    candidate_title: str,
    max_recent_posts: int = 15,
    recent_similarity_threshold: float = 0.70,
    cooldown_hours: float = 24.0,
    cooldown_similarity_threshold: float = 0.65,
    days_back: int = 30,
    general_similarity_threshold: float = 0.80,
) -> tuple[bool, str]:
    """
    Production anti-duplication & velocity guardrails:
    1. 15-Post Rule: Checks the last 15 posts in history. If similarity >= 0.70, rejected.
    2. 24h Trend Cooldown: If a similar topic (>= 0.65) was posted within 24 hours, rejected.
    3. 30-Day General Memory: If any post in the last 30 days has similarity >= 0.80, rejected.

    Returns: (is_duplicate: bool, reason: str)
    """
    history = load_post_history()
    if not history:
        return False, "History empty — pass"

    cand_vec = get_text_embedding(candidate_title)
    now = time.time()
    cooldown_cutoff = now - (cooldown_hours * 3600.0)
    days_cutoff = now - (days_back * 86400.0)

    # 1. 15-Post check (strict threshold)
    last_n_items = history[:max_recent_posts]
    for idx, item in enumerate(last_n_items, start=1):
        item_vec = item.get("embedding")
        if not item_vec:
            continue
        sim = cosine_similarity(cand_vec, item_vec)
        if sim >= recent_similarity_threshold:
            return True, f"15-Post Rule: Similar ({sim:.2f} >= {recent_similarity_threshold}) to post #{idx} ('{item.get('title')}')"

    # 2. 24h Trend Cooldown check
    for item in history:
        ts = item.get("timestamp", 0)
        if ts < cooldown_cutoff:
            continue
        item_vec = item.get("embedding")
        if not item_vec:
            continue
        sim = cosine_similarity(cand_vec, item_vec)
        if sim >= cooldown_similarity_threshold:
            hrs_ago = round((now - ts) / 3600.0, 1)
            return True, f"24h Trend Cooldown: Topic matches post from {hrs_ago}h ago ('{item.get('title')}', sim={sim:.2f})"

    # 3. 30-Day General Memory check
    for item in history:
        ts = item.get("timestamp", 0)
        if ts < days_cutoff:
            continue
        item_vec = item.get("embedding")
        if not item_vec:
            continue
        sim = cosine_similarity(cand_vec, item_vec)
        if sim >= general_similarity_threshold:
            return True, f"30-Day Memory: High similarity ({sim:.2f} >= {general_similarity_threshold}) with '{item.get('title')}'"

    return False, "Passed all deduplication guardrails"
