"""
core/analytics.py
-----------------
Post-Publishing Analytics & Meta Graph API Insights Engine:
1. Harvests post-publishing metrics (reach, impressions, saved, shares, likes, comments) via Graph API.
2. Computes weighted Engagement Score prioritizing high-intent actions (Saves x3, Shares x3).
3. Synchronizes metrics to Supabase PostgreSQL and local vector memory.
4. Generates performance feedback signals for the 5-Stage AI Topic Funnel.
"""

import os
import json
import time
import random
import requests
from typing import Dict, Any, List, Optional
from pathlib import Path

from .utils import logger
from .publisher import get_graph_api_base
from .database import update_post_insights_in_supabase, fetch_posts_from_supabase
from .memory import load_post_history, MEMORY_FILE_PATH, get_text_embedding


def calculate_engagement_score(metrics: Dict[str, Any]) -> float:
    """
    Computes weighted educational engagement score:
    - Saves (3.0x): Direct indicator of actionable utility.
    - Shares (3.0x): Organic viral distribution signal.
    - Comments (2.0x): High algorithmic engagement factor.
    - Likes (1.0x): Standard passive validation.
    """
    saved = float(metrics.get("saved", 0))
    shares = float(metrics.get("shares", 0))
    comments = float(metrics.get("comments", 0))
    likes = float(metrics.get("likes", 0))

    score = (saved * 3.0) + (shares * 3.0) + (comments * 2.0) + (likes * 1.0)
    return round(score, 1)


def classify_resonance_tier(engagement_score: float) -> str:
    """Classifies post into performance resonance tiers."""
    if engagement_score >= 100.0:
        return "VIRAL_TIER"
    elif engagement_score >= 40.0:
        return "TOP_PERFORMER"
    elif engagement_score >= 15.0:
        return "ABOVE_AVERAGE"
    return "NORMAL"


def fetch_instagram_post_insights(post_id: str) -> Dict[str, Any]:
    """
    Queries Meta Graph API for post insights:
    - /{media-id}/insights?metric=impressions,reach,saved,shares,total_interactions
    - /{media-id}?fields=like_count,comments_count
    Returns structured metrics dictionary.
    """
    access_token = os.environ.get("IG_ACCESS_TOKEN")
    api_base = get_graph_api_base(access_token)

    metrics = {
        "post_id": post_id,
        "reach": 0,
        "impressions": 0,
        "saved": 0,
        "shares": 0,
        "likes": 0,
        "comments": 0,
        "engagement_score": 0.0,
        "resonance_tier": "NORMAL",
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "is_mock": False,
    }

    if not access_token or not post_id or post_id.startswith("mock_"):
        # Simulated fallback for local testing & dry-runs
        sim_reach = random.randint(1200, 8500)
        metrics.update({
            "reach": sim_reach,
            "impressions": int(sim_reach * 1.35),
            "saved": random.randint(35, 240),
            "shares": random.randint(20, 110),
            "likes": random.randint(80, 450),
            "comments": random.randint(12, 65),
            "is_mock": True,
        })
        metrics["engagement_score"] = calculate_engagement_score(metrics)
        metrics["resonance_tier"] = classify_resonance_tier(metrics["engagement_score"])
        return metrics

    try:
        # 1. Fetch like_count and comments_count
        resp_media = requests.get(
            f"{api_base}/{post_id}",
            params={"fields": "like_count,comments_count", "access_token": access_token},
            timeout=15,
        )
        if resp_media.status_code == 200:
            m_data = resp_media.json()
            metrics["likes"] = m_data.get("like_count", 0)
            metrics["comments"] = m_data.get("comments_count", 0)

        # 2. Fetch insights
        resp_insights = requests.get(
            f"{api_base}/{post_id}/insights",
            params={
                "metric": "impressions,reach,saved,shares,total_interactions",
                "access_token": access_token,
            },
            timeout=15,
        )
        if resp_insights.status_code == 200:
            i_data = resp_insights.json().get("data", [])
            for item in i_data:
                name = item.get("name")
                val = 0
                values = item.get("values", [])
                if values and "value" in values[0]:
                    val = values[0]["value"]
                elif "total_value" in item:
                    val = item["total_value"].get("value", 0)

                if name == "reach":
                    metrics["reach"] = int(val)
                elif name == "impressions":
                    metrics["impressions"] = int(val)
                elif name == "saved":
                    metrics["saved"] = int(val)
                elif name == "shares":
                    metrics["shares"] = int(val)
        else:
            logger.debug("Graph API insights returned %d: %s", resp_insights.status_code, resp_insights.text[:100])

    except Exception as e:
        logger.warning("Error fetching Graph API insights for %s: %s", post_id, e)

    metrics["engagement_score"] = calculate_engagement_score(metrics)
    metrics["resonance_tier"] = classify_resonance_tier(metrics["engagement_score"])
    return metrics


def audit_published_posts_insights(
    max_posts: int = 15,
    fallback_seed_if_empty: bool = True,
) -> Dict[str, Any]:
    """
    Audits recently published posts, fetches live metrics, updates Supabase,
    and enriches local vector memory (data/post_history.json).
    """
    logger.info("📊 Starting Post-Publishing Analytics Audit via Meta Graph API & Supabase...")

    # 1. Fetch from Supabase
    supabase_posts = fetch_posts_from_supabase(limit=max_posts)
    local_history = load_post_history()

    audited_count = 0
    top_performers = []

    # Map to track and update local history
    history_by_title = {p.get("title"): p for p in local_history if p.get("title")}

    posts_to_check = []
    # Collect all posts from Supabase or local history
    for sp in supabase_posts:
        meta = sp.get("metadata") or {}
        post_id = meta.get("post_id")
        title = sp.get("title")
        if title:
            posts_to_check.append({
                "title": title,
                "post_id": post_id or f"mock_{abs(hash(title)) % 100000}",
                "category": sp.get("category", "AI & CODING"),
                "source": "supabase",
            })

    # If Supabase has few posts, also check local_history
    for lh in local_history:
        title = lh.get("title")
        if title and not any(p["title"] == title for p in posts_to_check):
            posts_to_check.append({
                "title": title,
                "post_id": lh.get("post_id") or f"mock_{abs(hash(title)) % 100000}",
                "category": lh.get("category", "AI & CODING"),
                "source": "local",
            })

    if not posts_to_check and fallback_seed_if_empty:
        # Seed default historical topics so feedback loop works immediately
        seed_topics = [
            ("5 Python Performance Tips for AI Engineers", "AI & CODING", 128.0),
            ("FastAPI High-Throughput Microservice Blueprint", "AI & CODING", 164.0),
            ("Cursor Pro vs. Continue.dev + Ollama", "AI & CODING", 142.0),
        ]
        for t, cat, score in seed_topics:
            sim_metrics = {
                "post_id": f"seed_{abs(hash(t)) % 100000}",
                "reach": 5400,
                "impressions": 7200,
                "saved": int(score * 0.45),
                "shares": int(score * 0.35),
                "likes": 220,
                "comments": 34,
                "engagement_score": score,
                "resonance_tier": "TOP_PERFORMER",
                "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                "is_mock": True,
            }
            update_post_insights_in_supabase(sim_metrics["post_id"], sim_metrics, title=t)
            top_performers.append({"title": t, "score": score, "metrics": sim_metrics})
            audited_count += 1

    for p in posts_to_check[:max_posts]:
        title = p["title"]
        post_id = p["post_id"]

        insights = fetch_instagram_post_insights(post_id)
        score = insights.get("engagement_score", 0.0)

        # Update Supabase
        update_post_insights_in_supabase(post_id, insights, title=title)

        # Update local memory
        if title in history_by_title:
            history_by_title[title]["insights"] = insights
            history_by_title[title]["engagement_score"] = score
        else:
            local_history.append({
                "title": title,
                "category": p.get("category", "AI & CODING"),
                "timestamp": time.time(),
                "embedding": get_text_embedding(title),
                "insights": insights,
                "engagement_score": score,
            })

        if score >= 35.0:
            top_performers.append({"title": title, "score": score, "metrics": insights})
        audited_count += 1

    # Save updated local history
    try:
        MEMORY_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(MEMORY_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(local_history, f, indent=2)
    except Exception as e:
        logger.warning("Could not persist updated insights to post_history.json: %s", e)

    summary = {
        "audited_count": audited_count,
        "top_performers_count": len(top_performers),
        "top_performers": sorted(top_performers, key=lambda x: x["score"], reverse=True),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
    }

    logger.info("  ✓ Analytics Audit Complete: %d posts audited, %d identified as Top Performers.", audited_count, len(top_performers))
    return summary
