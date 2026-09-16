"""
core/database.py
----------------
Supabase Database Integration:
Persists generated post topics, structured carousel plans, vector embeddings,
and publishing logs to Supabase for cloud analytics and cross-device sync.
"""

import os
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from .utils import logger

try:
    from supabase import create_client, Client
except ImportError:
    create_client = None
    Client = Any


def get_supabase_client(require_admin: bool = False) -> Optional[Client]:
    """
    Initializes and returns the Supabase client using environment variables.
    Prefers SUPABASE_SERVICE_ROLE_KEY for server operations.
    If require_admin is True, strictly requires SUPABASE_SERVICE_ROLE_KEY to prevent
    unauthorized write attempts under RLS.
    """
    if create_client is None:
        return None

    url = os.environ.get("SUPABASE_URL")
    admin_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    anon_key = os.environ.get("SUPABASE_ANON_KEY")

    if not url:
        return None

    if require_admin:
        if not admin_key:
            logger.warning("Supabase admin client requested but SUPABASE_SERVICE_ROLE_KEY is not set.")
            return None
        key = admin_key
    else:
        key = admin_key or anon_key

    if not key:
        return None

    try:
        return create_client(url, key)
    except Exception as e:
        logger.warning("Failed to initialize Supabase client: %s", e)
        return None


def sync_post_to_supabase(
    title: str,
    category: str = "AI & CODING",
    hook: str = "",
    embedding: Optional[List[float]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    post_id: Optional[str] = None,
    format_type: Optional[str] = None,
    slide_urls: Optional[List[str]] = None,
    caption: Optional[str] = None,
    auto_comment: Optional[str] = None,
    insights: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Saves or updates a published post with complete metadata into Supabase 'posts' table.
    Requires admin privileges to write under Row-Level Security.
    """
    client = get_supabase_client(require_admin=True)
    if not client:
        return False

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
    if embedding:
        meta["embedding"] = embedding
    if insights:
        meta["insights"] = insights
    meta.setdefault("status", "published")

    row = {
        "title": title,
        "category": category,
        "hook": hook,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "metadata": meta,
    }

    try:
        # Check if row with this title or post_id already exists to update
        existing = client.table("posts").select("id, metadata").eq("title", title).limit(1).execute()
        if existing.data and len(existing.data) > 0:
            row_id = existing.data[0]["id"]
            merged_meta = dict(existing.data[0].get("metadata") or {})
            merged_meta.update(meta)
            client.table("posts").update({"metadata": merged_meta, "hook": hook, "category": category}).eq("id", row_id).execute()
            logger.info("  ✓ Updated existing post in Supabase: \"%s\" (ID: %s)", title, row_id)
            return True

        client.table("posts").insert(row).execute()
        logger.info("  ✓ Inserted new post into Supabase: \"%s\"", title)
        return True
    except Exception as e:
        logger.warning("Supabase sync notice: %s", e)
        return False


def update_post_insights_in_supabase(
    post_id: str,
    insights: Dict[str, Any],
    title: Optional[str] = None,
) -> bool:
    """
    Updates the performance metrics and engagement score for a specific post in Supabase.
    Requires admin privileges to modify records under Row-Level Security.
    """
    client = get_supabase_client(require_admin=True)
    if not client:
        return False

    try:
        # Query post by title or metadata->>post_id
        resp = None
        if title:
            resp = client.table("posts").select("id, metadata").eq("title", title).limit(1).execute()

        if not resp or not resp.data:
            resp = client.table("posts").select("id, metadata").contains("metadata", {"post_id": post_id}).limit(1).execute()

        if resp and resp.data and len(resp.data) > 0:
            row_id = resp.data[0]["id"]
            meta = dict(resp.data[0].get("metadata") or {})
            meta["insights"] = insights
            meta["last_audited_at"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            client.table("posts").update({"metadata": meta}).eq("id", row_id).execute()
            logger.info("  ✓ Successfully updated Supabase insights for post ID %s (Score: %.1f)", post_id, insights.get("engagement_score", 0.0))
            return True

        logger.debug("Post %s not found in Supabase to update insights.", post_id)
        return False
    except Exception as e:
        logger.warning("Failed to update insights in Supabase for %s: %s", post_id, e)
        return False


def fetch_posts_from_supabase(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Fetches recent posts from Supabase 'posts' table.
    """
    client = get_supabase_client()
    if not client:
        return []

    try:
        resp = client.table("posts").select("*").order("created_at", desc=True).limit(limit).execute()
        return resp.data or []
    except Exception as e:
        logger.warning("Could not fetch posts from Supabase: %s", e)
        return []


def fetch_top_performing_posts_from_supabase(
    min_engagement_score: float = 10.0,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Retrieves historical top-performing posts from Supabase based on engagement score.
    Used by the topic discovery feedback loop.
    """
    posts = fetch_posts_from_supabase(limit=100)
    winners = []
    for p in posts:
        meta = p.get("metadata") or {}
        insights = meta.get("insights") or {}
        score = insights.get("engagement_score", 0.0)
        if score >= min_engagement_score:
            winners.append({
                "title": p.get("title"),
                "category": p.get("category"),
                "engagement_score": score,
                "saved": insights.get("saved", 0),
                "shares": insights.get("shares", 0),
                "reach": insights.get("reach", 0),
                "embedding": meta.get("embedding"),
            })

    winners.sort(key=lambda x: x["engagement_score"], reverse=True)
    return winners[:limit]


def fetch_posts_needing_audit_from_supabase(hours_old: int = 24) -> List[Dict[str, Any]]:
    """
    Retrieves published posts that are at least `hours_old` hours old and need an insights audit.
    """
    posts = fetch_posts_from_supabase(limit=50)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_old)
    needing_audit = []

    for p in posts:
        meta = p.get("metadata") or {}
        post_id = meta.get("post_id")
        created_str = p.get("created_at")
        if not post_id or not created_str:
            continue

        try:
            # Parse created_at format
            created_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)

            if created_dt <= cutoff:
                needing_audit.append(p)
        except Exception:
            continue

    return needing_audit
