"""
core/database.py
----------------
Supabase Database Integration:
Persists generated post topics, structured carousel plans, vector embeddings,
and publishing logs to Supabase for cloud analytics and cross-device sync.
"""

import os
import time
from typing import List, Dict, Any, Optional
from .utils import logger

try:
    from supabase import create_client, Client
except ImportError:
    create_client = None
    Client = Any


def get_supabase_client() -> Optional[Client]:
    """
    Initializes and returns the Supabase client using environment variables.
    Prefers SUPABASE_SERVICE_ROLE_KEY for server operations, falls back to SUPABASE_ANON_KEY.
    """
    if create_client is None:
        return None

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY")

    if not url or not key:
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
) -> bool:
    """
    Saves a generated/published post to the 'posts' table in Supabase.
    Safe: Fails gracefully if the table does not exist or network is offline.
    """
    client = get_supabase_client()
    if not client:
        return False

    row = {
        "title": title,
        "category": category,
        "hook": hook,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "metadata": metadata or {},
    }

    try:
        client.table("posts").insert(row).execute()
        return True
    except Exception as e:
        logger.warning("Supabase sync notice (table 'posts' may not exist yet): %s", e)
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
