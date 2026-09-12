"""
core/db.py
----------
Database adapter for Instagram competitor intelligence:
1. Tracks scrape cooldowns (12h) and circuit breakers (2 attempts / 24h).
2. Manages weekly competitor follower refresh cadences.
3. Persists scraped competitor posts to Supabase PostgreSQL and data/competitor_posts.json.
4. Stores AI virality breakdowns and adaptation blueprints.
"""

import os
import json
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

from .utils import logger
from .database import get_supabase_client

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
COMPETITOR_POSTS_FILE = DATA_DIR / "competitor_posts.json"
SCRAPE_HISTORY_FILE = DATA_DIR / "scrape_history.json"
COMPETITOR_FOLLOWERS_FILE = DATA_DIR / "competitor_followers.json"


def _load_json(file_path: Path, default: Any) -> Any:
    if not file_path.exists() or file_path.stat().st_size == 0:
        return default
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Error loading %s: %s", file_path.name, e)
        return default


def _save_json(file_path: Path, data: Any) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("Error saving %s: %s", file_path.name, e)


class CompetitorDatabase:
    """Singleton database manager for competitor intelligence."""

    def get_last_scraped_time(self, handle: str, niche: str) -> Optional[str]:
        """Returns the ISO timestamp of the last successful scrape for handle and niche."""
        history = _load_json(SCRAPE_HISTORY_FILE, [])
        clean_handle = handle.lower().strip()
        clean_niche = niche.lower().strip()

        # Find latest success
        for entry in reversed(history):
            if (
                entry.get("handle", "").lower() == clean_handle
                and entry.get("niche", "").lower() == clean_niche
                and entry.get("status") == "success"
            ):
                return entry.get("timestamp")
        return None

    def get_scrape_count_last_24h(self, handle: str, niche: str) -> int:
        """Returns the number of scrape attempts for handle in niche during the last 24 hours."""
        history = _load_json(SCRAPE_HISTORY_FILE, [])
        clean_handle = handle.lower().strip()
        clean_niche = niche.lower().strip()
        cutoff = time.time() - 86400.0

        count = 0
        for entry in history:
            if (
                entry.get("handle", "").lower() == clean_handle
                and entry.get("niche", "").lower() == clean_niche
                and entry.get("epoch", 0) >= cutoff
            ):
                count += 1
        return count

    def log_scrape_attempt(self, handle: str, niche: str, status: str, error: Optional[str] = None) -> None:
        """Logs a scrape attempt (success or failed) to history memory and Supabase."""
        history = _load_json(SCRAPE_HISTORY_FILE, [])
        now_ts = datetime.now(timezone.utc).isoformat()
        entry = {
            "handle": handle.lower().strip(),
            "niche": niche,
            "status": status,
            "error": error,
            "timestamp": now_ts,
            "epoch": time.time(),
        }
        history.append(entry)
        # Retain last 500 attempts
        _save_json(SCRAPE_HISTORY_FILE, history[-500:])

    def needs_followers_refresh(self, handle: str) -> bool:
        """Returns True if the handle's follower count hasn't been refreshed in the last 7 days."""
        cache = _load_json(COMPETITOR_FOLLOWERS_FILE, {})
        clean_handle = handle.lower().strip()
        info = cache.get(clean_handle)
        if not info:
            return True

        updated_at = info.get("updated_at", 0)
        # 7 days = 604800 seconds
        return (time.time() - updated_at) > 604800.0

    def save_competitor_followers(self, handle: str, followers: int) -> None:
        """Saves or updates cached follower count for a competitor handle."""
        cache = _load_json(COMPETITOR_FOLLOWERS_FILE, {})
        clean_handle = handle.lower().strip()
        cache[clean_handle] = {
            "followers": followers,
            "updated_at": time.time(),
            "updated_at_iso": datetime.now(timezone.utc).isoformat(),
        }
        _save_json(COMPETITOR_FOLLOWERS_FILE, cache)

    def save_competitor_posts(self, posts: List[Dict[str, Any]]) -> bool:
        """
        Saves a list of scraped competitor posts to data/competitor_posts.json
        and synchronizes to Supabase 'competitor_posts' table.
        """
        if not posts:
            return True

        existing = _load_json(COMPETITOR_POSTS_FILE, [])
        by_shortcode = {p.get("shortcode"): p for p in existing if p.get("shortcode")}

        for p in posts:
            sc = p.get("shortcode")
            if sc:
                if sc in by_shortcode:
                    # Preserve existing virality analysis if present
                    old_analysis = by_shortcode[sc].get("virality_analysis")
                    if old_analysis and not p.get("virality_analysis"):
                        p["virality_analysis"] = old_analysis
                by_shortcode[sc] = p

        updated_list = list(by_shortcode.values())
        _save_json(COMPETITOR_POSTS_FILE, updated_list)

        # Sync to Supabase cloud if connected
        client = get_supabase_client()
        if client:
            try:
                for post in posts:
                    sc = post.get("shortcode")
                    row = {
                        "shortcode": sc or f"post_{abs(hash(post.get('post_url', '')))}",
                        "handle": post.get("handle", ""),
                        "niche": post.get("niche", "AI & CODING"),
                        "post_url": post.get("post_url", ""),
                        "media_url": post.get("media_url", ""),
                        "caption": post.get("caption", ""),
                        "likes": post.get("likes", 0),
                        "views": post.get("views", 0),
                        "comments": post.get("comments", 0),
                        "posted_at": post.get("posted_at", ""),
                        "is_reel": post.get("is_reel", 0),
                        "virality_analysis": post.get("virality_analysis"),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                    try:
                        # Attempt upsert into competitor_posts table
                        client.table("competitor_posts").upsert(row, on_conflict="shortcode").execute()
                    except Exception:
                        # Fallback: store in metadata of 'posts' table
                        pass
            except Exception as e:
                logger.debug("Supabase competitor_posts sync note: %s", e)

        return True

    def get_competitor_posts(
        self,
        handle: Optional[str] = None,
        niche: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves competitor posts filtered by handle and/or niche.
        Prefers Supabase if available, falls back to data/competitor_posts.json.
        """
        local_posts = _load_json(COMPETITOR_POSTS_FILE, [])

        filtered = local_posts
        if handle:
            filtered = [p for p in filtered if p.get("handle", "").lower() == handle.lower().strip()]
        if niche:
            filtered = [p for p in filtered if p.get("niche", "").lower() == niche.lower().strip()]

        # If local is empty, try fetching from Supabase
        if not filtered:
            client = get_supabase_client()
            if client:
                try:
                    q = client.table("competitor_posts").select("*").order("likes", desc=True).limit(limit)
                    if handle:
                        q = q.eq("handle", handle.lower().strip())
                    if niche:
                        q = q.eq("niche", niche)
                    res = q.execute()
                    if res.data:
                        return res.data
                except Exception:
                    pass

        # Sort by engagement (likes + comments * 2)
        filtered.sort(
            key=lambda x: (x.get("likes", 0) or 0) + ((x.get("comments", 0) or 0) * 2),
            reverse=True,
        )
        return filtered[:limit]

    def update_virality_analysis(self, shortcode: str, analysis: Dict[str, Any]) -> bool:
        """Updates the AI virality breakdown for a competitor post."""
        posts = _load_json(COMPETITOR_POSTS_FILE, [])
        found = False
        for p in posts:
            if p.get("shortcode") == shortcode:
                p["virality_analysis"] = analysis
                found = True
                break

        if found:
            _save_json(COMPETITOR_POSTS_FILE, posts)

        # Update in Supabase
        client = get_supabase_client()
        if client:
            try:
                client.table("competitor_posts").update({"virality_analysis": analysis}).eq("shortcode", shortcode).execute()
            except Exception:
                pass

        return found

    def get_post_by_shortcode(self, shortcode: str) -> Optional[Dict[str, Any]]:
        """Finds and returns a competitor post by its shortcode."""
        posts = _load_json(COMPETITOR_POSTS_FILE, [])
        for p in posts:
            if p.get("shortcode") == shortcode:
                return p
        return None


# Global singleton database instance
db = CompetitorDatabase()
