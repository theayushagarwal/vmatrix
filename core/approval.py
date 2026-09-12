"""
core/approval.py
----------------
30-Minute Human Approval Queue & Governance Engine.

Provides an enterprise-grade grace period workflow for autonomous social publishing:
1. When a post is generated (on-demand or scheduled cron), it enters the approval queue.
2. A 30-minute countdown timer is initiated.
3. A human operator can review the 2160x2700 Retina slides, vision audit score, caption,
   and auto-comment in the dashboard.
4. Actions:
   - 🚀 Approve & Publish Now: Instantly publishes to Instagram and auto-comments.
   - ⏱️ Extend Timer (+15 Mins): Extends the grace period countdown.
   - ✏️ Save Edits: Persists copy adjustments before release.
   - ❌ Reject Post: Cancels publication and logs rejection reason.
5. Failover / Auto-Pilot: If the 30-minute timer expires with no human intervention,
   the post automatically self-approves and publishes to Instagram.
"""

import os
import json
import time
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from .publisher import (
    upload_images_to_cloudinary,
    publish_to_instagram_photo,
    publish_to_instagram_carousel,
    post_instagram_comment,
    get_graph_api_base,
)
from .memory import record_post
from .utils import logger

QUEUE_FILE_PATH = Path(__file__).resolve().parent.parent / "data" / "approval_queue.json"
QUEUE_MEDIA_DIR = Path(__file__).resolve().parent.parent / "data" / "queue_media"


def _ensure_storage():
    """Ensures queue data file and media directories exist."""
    QUEUE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    if not QUEUE_FILE_PATH.exists():
        with open(QUEUE_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)


def load_approval_queue() -> List[Dict[str, Any]]:
    """Loads all queued posts from persistent JSON storage."""
    _ensure_storage()
    try:
        with open(QUEUE_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.error("Failed to load approval queue: %s", e)
        return []


def save_approval_queue(queue: List[Dict[str, Any]]) -> None:
    """Atomically saves the approval queue to disk."""
    _ensure_storage()
    temp_file = QUEUE_FILE_PATH.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2, ensure_ascii=False)
    temp_file.replace(QUEUE_FILE_PATH)


def queue_post_for_approval(
    topic: str,
    format_type: str,
    slot: str,
    slide_paths: List[Path],
    caption: str,
    auto_comment: str,
    content_plan: Optional[Dict[str, Any]] = None,
    vision_score: float = 10.0,
    vision_method: str = "pil_retina_analyzer",
    timeout_minutes: int = 30,
    upload_cdn_now: bool = True,
) -> Dict[str, Any]:
    """
    Places a rendered post into the approval queue with a 30-minute timer.
    Copies local slides into persistent queue media storage and optionally
    pre-uploads to Cloudinary so visual previews are instantly available.
    """
    _ensure_storage()
    now = time.time()
    item_id = f"appr_{int(now)}_{os.urandom(3).hex()}"
    expires_at = now + (timeout_minutes * 60)

    # 1. Persist local slide copies
    item_media_dir = QUEUE_MEDIA_DIR / item_id
    item_media_dir.mkdir(parents=True, exist_ok=True)
    saved_slide_paths = []
    for idx, sp in enumerate(slide_paths):
        dest = item_media_dir / f"slide_{idx + 1}{sp.suffix}"
        shutil.copy2(sp, dest)
        saved_slide_paths.append(str(dest))

    # 2. Optionally pre-upload to Cloudinary
    image_urls = []
    if upload_cdn_now:
        try:
            logger.info("  ⚡ Pre-uploading %d slides to Cloudinary for instant queue preview...", len(saved_slide_paths))
            image_urls = upload_images_to_cloudinary([Path(p) for p in saved_slide_paths])
        except Exception as e:
            logger.warning("Cloudinary pre-upload failed (will retry at publish time): %s", e)

    queued_item: Dict[str, Any] = {
        "id": item_id,
        "topic": topic,
        "category": (content_plan or {}).get("category", "AI & CODING"),
        "format": format_type,
        "slot": slot,
        "created_at": now,
        "created_at_iso": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "expires_at": expires_at,
        "timeout_minutes": timeout_minutes,
        "status": "pending",  # "pending", "approved", "auto_published", "rejected"
        "vision_score": vision_score,
        "vision_method": vision_method,
        "content_plan": content_plan or {},
        "slide_paths": saved_slide_paths,
        "image_urls": image_urls,
        "caption": caption,
        "auto_comment": auto_comment,
        "post_id": None,
        "comment_id": None,
        "permalink": None,
        "rejection_reason": None,
        "action_taken_at": None,
    }

    queue = load_approval_queue()
    queue.insert(0, queued_item)
    save_approval_queue(queue)

    logger.info(
        "⏱️ Enqueued post '%s' (%s) with %d-min approval timer. Expires at: %s",
        topic, item_id, timeout_minutes,
        datetime.fromtimestamp(expires_at, tz=timezone.utc).strftime("%H:%M:%S UTC"),
    )
    return queued_item


def get_pending_approvals() -> List[Dict[str, Any]]:
    """Returns all active posts waiting for human approval, ordered by expiration."""
    queue = load_approval_queue()
    pending = [item for item in queue if item.get("status") == "pending"]
    # Sort so closest to expiration comes first
    pending.sort(key=lambda x: x.get("expires_at", 0))
    return pending


def get_approval_history(limit: int = 30) -> List[Dict[str, Any]]:
    """Returns past resolved posts (approved, auto_published, rejected)."""
    queue = load_approval_queue()
    history = [item for item in queue if item.get("status") != "pending"]
    history.sort(key=lambda x: x.get("action_taken_at") or x.get("created_at", 0), reverse=True)
    return history[:limit]


def get_time_remaining(item: Dict[str, Any]) -> Tuple[int, int, float]:
    """
    Computes time remaining before auto-publish.
    Returns: (minutes, seconds, fraction_remaining [0.0 to 1.0])
    """
    now = time.time()
    expires_at = item.get("expires_at", now)
    created_at = item.get("created_at", now - 1800)
    total_window = max(1.0, expires_at - created_at)

    remaining_seconds = max(0.0, expires_at - now)
    fraction = min(1.0, max(0.0, remaining_seconds / total_window))

    mins = int(remaining_seconds // 60)
    secs = int(remaining_seconds % 60)
    return mins, secs, fraction


def extend_approval_timeout(item_id: str, extra_minutes: int = 15) -> Dict[str, Any]:
    """Extends the 30-minute countdown timer by additional minutes."""
    queue = load_approval_queue()
    for item in queue:
        if item.get("id") == item_id and item.get("status") == "pending":
            item["expires_at"] = item.get("expires_at", time.time()) + (extra_minutes * 60)
            item["timeout_minutes"] = item.get("timeout_minutes", 30) + extra_minutes
            save_approval_queue(queue)
            logger.info("⏱️ Extended timer for %s by +%d minutes.", item_id, extra_minutes)
            return item
    raise ValueError(f"Pending queue item not found: {item_id}")


def update_queued_post(
    item_id: str,
    caption: Optional[str] = None,
    auto_comment: Optional[str] = None,
) -> Dict[str, Any]:
    """Persists copy modifications made by the human operator."""
    queue = load_approval_queue()
    for item in queue:
        if item.get("id") == item_id and item.get("status") == "pending":
            if caption is not None:
                item["caption"] = caption
            if auto_comment is not None:
                item["auto_comment"] = auto_comment
            save_approval_queue(queue)
            logger.info("✏️ Updated copy for queued post %s.", item_id)
            return item
    raise ValueError(f"Pending queue item not found: {item_id}")


def reject_queued_post(item_id: str, reason: str = "Rejected by operator") -> Dict[str, Any]:
    """Marks a post as rejected and cancels its scheduled publication."""
    queue = load_approval_queue()
    for item in queue:
        if item.get("id") == item_id and item.get("status") == "pending":
            item["status"] = "rejected"
            item["rejection_reason"] = reason
            item["action_taken_at"] = time.time()
            save_approval_queue(queue)
            logger.info("❌ Rejected queued post %s: %s", item_id, reason)
            return item
    raise ValueError(f"Pending queue item not found: {item_id}")


def approve_and_publish_post(item_id: str, auto: bool = False) -> Dict[str, Any]:
    """
    Approves a queued post and executes live publication to Instagram:
    1. Ensures slides are hosted on Cloudinary.
    2. Calls publish_to_instagram_photo or publish_to_instagram_carousel.
    3. Auto-posts the engagement first comment.
    4. Records topic in 30-day vector deduplication memory.
    5. Updates status to 'approved' (or 'auto_published').
    """
    queue = load_approval_queue()
    target_item = None
    for item in queue:
        if item.get("id") == item_id and item.get("status") == "pending":
            target_item = item
            break

    if not target_item:
        raise ValueError(f"Pending queue item not found: {item_id}")

    format_type = target_item.get("format", "listicle")
    caption = target_item.get("caption", "")
    auto_comment = target_item.get("auto_comment", "")
    image_urls = target_item.get("image_urls", [])
    slide_paths = [Path(p) for p in target_item.get("slide_paths", [])]

    # Ensure Cloudinary URLs are present
    if not image_urls:
        logger.info("  ⚡ Uploading %d slides to Cloudinary CDN...", len(slide_paths))
        image_urls = upload_images_to_cloudinary(slide_paths)
        target_item["image_urls"] = image_urls

    # Publish to Instagram
    logger.info("🚀 Publishing approved post %s (%s) live to Instagram...", item_id, format_type)
    if format_type == "photo":
        res = publish_to_instagram_photo(image_urls[0], caption, auto_comment=auto_comment)
    else:
        res = publish_to_instagram_carousel(image_urls, caption, auto_comment=auto_comment)

    post_id = res.get("post_id")
    comment_id = res.get("comment_id")

    # Fetch permalink if available
    permalink = None
    access_token = os.environ.get("IG_ACCESS_TOKEN")
    if post_id and access_token:
        try:
            import requests
            api_base = get_graph_api_base(access_token)
            p_res = requests.get(
                f"{api_base}/{post_id}",
                params={"fields": "permalink", "access_token": access_token},
                timeout=10,
            )
            if p_res.status_code == 200:
                permalink = p_res.json().get("permalink")
        except Exception:
            pass

    # Record to vector memory
    record_post(
        title=target_item.get("topic", "Approved Post"),
        category=target_item.get("category", "AI & CODING"),
        hook=(target_item.get("content_plan") or {}).get("hook_line", ""),
    )

    target_item["status"] = "auto_published" if auto else "approved"
    target_item["post_id"] = post_id
    target_item["comment_id"] = comment_id
    target_item["permalink"] = permalink
    target_item["action_taken_at"] = time.time()
    save_approval_queue(queue)

    logger.info("🎉 Post %s successfully published live! Post ID: %s | Link: %s", item_id, post_id, permalink)
    return target_item


def process_auto_publish_timeouts(auto_publish_enabled: bool = True) -> List[Dict[str, Any]]:
    """
    Heartbeat scanner: checks all pending items whose 30-minute timer has elapsed.
    If auto_publish_enabled is True, automatically publishes them to Instagram.
    """
    now = time.time()
    pending = get_pending_approvals()
    processed = []

    for item in pending:
        if now >= item.get("expires_at", now + 99999):
            logger.info("⏳ 30-Minute grace period expired for %s ('%s')", item['id'], item['topic'])
            if auto_publish_enabled:
                try:
                    result = approve_and_publish_post(item["id"], auto=True)
                    processed.append(result)
                except Exception as e:
                    logger.error("❌ Failed to auto-publish expired item %s: %s", item['id'], e)
    return processed
