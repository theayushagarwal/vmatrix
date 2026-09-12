"""
schedulers/daily.py
-------------------
Daily Competitor Scraping & Filtering Scheduler:
1. Ingests scraped competitor posts from Apify.
2. Filters out non-tech and off-niche lifestyle posts using config/niches.yaml keyword gate.
3. Saves only approved niche posts to the database via db.upsert_competitor_post().
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml
from loguru import logger

from core.db import db
from core.scraper import InstaScraper

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config" / "niches.yaml"


def load_niche_config(niche_name: str = "veltrix") -> Dict[str, Any]:
    """Loads niche definition and keywords_filter list from config/niches.yaml."""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                niches = data.get("niches", {})
                if niche_name in niches:
                    return niches[niche_name]
                # Default fallback to veltrix or first defined niche
                if "veltrix" in niches:
                    return niches["veltrix"]
                if niches:
                    return next(iter(niches.values()))
        except Exception as e:
            logger.warning(f"Failed to parse niche config at {CONFIG_PATH}: {e}")

    # Fallback default terms if config file is inaccessible
    return {
        "description": "AI, Quant Finance, Coding",
        "keywords_filter": [
            "ai", "finance", "fintech", "trading", "stocks", "chatgpt",
            "wealth", "claude", "gemini", "tech", "playwright", "automation",
            "openai", "python", "coding", "crypto", "nvidia", "investing"
        ]
    }


import re


def matches_keyword(caption: str, keyword: str) -> bool:
    """Matches keyword against caption with word-boundary protection for short tokens."""
    k = keyword.lower().strip()
    if not k:
        return False
    if len(k) <= 2:
        # Prevent 'ai' from matching 'mumbai', 'again', 'daily', etc.
        return bool(re.search(rf"(?:\b|#){re.escape(k)}(?:\b|[0-9_]|\s|[.,!?/])", caption))
    return k in caption


def filter_and_save_competitor_posts(
    handle: str,
    posts: List[Dict[str, Any]],
    niche_name: str = "veltrix"
) -> List[Dict[str, Any]]:
    """
    Scans each post caption against the configured niche keyword gate.
    Skips non-tech or off-niche posts and persists only approved posts.
    """
    niche = load_niche_config(niche_name)
    keywords = niche.get("keywords_filter", [])
    filtered_posts = []

    for post in posts:
        if keywords:
            caption = (post.get("caption") or "").lower()

            # ❌ If NO niche keywords appear in the caption, SKIP the post
            if not any(matches_keyword(caption, k) for k in keywords):
                continue

        # ✅ Only approved niche posts are saved to the database
        db.upsert_competitor_post(post)
        filtered_posts.append(post)

    if posts:
        logger.info(f"  ✓ @{handle}: {len(filtered_posts)} posts (filtered from {len(posts)})")

    return filtered_posts


def run_daily_scraping_job(
    handles: Optional[List[str]] = None,
    niche_name: str = "veltrix",
    limit: int = 6
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Executes daily competitor scraping batch with strict keyword gate filtering.
    """
    target_handles = handles or ["bytebytego_", "thecodebytes", "bhavik.dev"]
    logger.info(f"Starting daily competitor scraping for {len(target_handles)} handles (niche: {niche_name})...")

    scraper = InstaScraper()
    batch_results = scraper.scrape_batch(target_handles, niche="AI & CODING", limit=limit)

    results = {}
    for handle in target_handles:
        posts = batch_results.get(handle, [])
        filtered = filter_and_save_competitor_posts(handle, posts, niche_name=niche_name)
        results[handle] = filtered

    return results


if __name__ == "__main__":
    run_daily_scraping_job()
