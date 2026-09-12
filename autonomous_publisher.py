"""
autonomous_publisher.py
-----------------------
Fully autonomous pipeline runner designed for GitHub Actions and cron jobs:
1. Resolves publishing slot & format according to 7-Day Weekly Content Calendar:
   - 🌅 Morning Slot (7:00 AM IST / 01:30 UTC): Always Single Photo Infographic / Cheatsheet.
   - 🌆 Evening Slot (7:00 PM IST / 13:30 UTC):
       - Thursday & Saturday: Architecture Flowchart Carousel ('flow').
       - Monday, Tuesday, Wednesday, Friday, Sunday: 5-Slide Educational Listicle ('listicle').
2. Harvests live signals from 4 data feeds (Google Trends, TechCrunch AI, VentureBeat AI, Hacker News).
3. Filters signals through the 5-Stage AI Funnel with 15-post & 24h trend anti-duplication guardrails.
4. Selects the #1 highest-scoring winning topic.
5. Plans structured content with Groq (openai/gpt-oss-120b with failover).
6. Renders 2160x2700 Retina slides using batch in-memory Playwright (95% JPEG).
7. Uploads media to Cloudinary CDN.
8. Publishes live to Instagram via Meta Graph API (Single Photo or Multi-Slide Carousel).
9. Syncs to Supabase cloud database & updates 30-day post history memory.
"""

import os
import sys
import argparse
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

# Ensure stdout handles UTF-8 on Windows and Linux runners
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv()

from core import (
    fetch_all_feeds,
    run_filtering_funnel,
    generate_carousel_content,
    generate_cheatsheet_content,
    generate_flow_carousel_content,
    render_carousel_slides,
    render_listicle_slides,
    render_carousel_flow_slides,
    render_infographic,
    upload_images_to_cloudinary,
    publish_to_instagram_carousel,
    publish_to_instagram_photo,
    post_instagram_comment,
    audit_slide_images,
    generate_post_caption,
    generate_post_comment,
    record_post,
    get_time_since_last_post,
    queue_post_for_approval,
    audit_published_posts_insights,
)
from core.utils import logger


WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def resolve_slot_and_format(slot: str = "auto", format_override: str = "auto") -> tuple[str, str]:
    """
    Resolves the active publishing slot ('morning' vs 'evening') and the format
    ('photo', 'listicle', 'flow') according to the 7-day weekly schedule:

    ⏰ Slot 1: Morning (01:30 UTC / 7:00 AM IST):
       - ALWAYS Single Photo Infographic / Cheatsheet ('photo') across all 7 days.
       - Replaces all legacy video/reel slots.

    🌆 Slot 2: Evening (13:30 UTC / 7:00 PM IST):
       - Thursday (3) & Saturday (5): 'flow' (System Architecture Flowchart Carousel)
       - Monday (0), Tuesday (1), Wednesday (2), Friday (4), Sunday (6): 'listicle' (5-slide Educational Carousel)
    """
    now_utc = datetime.now(timezone.utc)
    weekday = now_utc.weekday()  # 0=Monday ... 6=Sunday

    # 1. Determine Slot
    if slot == "auto":
        # Morning window: 00:00 to 07:59 UTC (Centered around 01:30 UTC)
        # Evening window: 08:00 to 23:59 UTC (Centered around 13:30 UTC)
        active_slot = "morning" if now_utc.hour < 8 else "evening"
    else:
        active_slot = slot.lower()

    # 2. If format is explicitly overridden, respect it
    if format_override and format_override != "auto":
        return active_slot, format_override.lower()

    # 3. Resolve format based on slot & weekday content calendar
    if active_slot == "morning":
        # Morning slot is always Single Photo Cheatsheet
        resolved_format = "photo"
    else:
        # Evening slot: Architecture Flow on Thursday (3) and Saturday (5)
        if weekday in (3, 5):
            resolved_format = "flow"
        else:
            resolved_format = "listicle"

    return active_slot, resolved_format


def run_autonomous_post(
    dry_run: bool = False,
    forced_topic: str | None = None,
    slot: str = "auto",
    format_override: str = "auto",
    geo: str = "IN",
    queue_for_approval: bool = False,
    timeout_minutes: int = 30,
) -> dict:
    """
    Executes the full end-to-end autonomous publishing loop.
    Returns summary execution dictionary.
    """
    start_time = time.time()
    now_utc = datetime.now(timezone.utc)
    day_name = WEEKDAY_NAMES[now_utc.weekday()]

    active_slot, pipeline_mode = resolve_slot_and_format(slot, format_override)

    logger.info("=" * 65)
    logger.info("🚀 STARTING AUTONOMOUS SOCIAL ENGINE PIPELINE")
    logger.info("📅 Schedule: %s | Active Slot: %s | Mode: %s", day_name, active_slot.upper(), pipeline_mode.upper())
    logger.info("=" * 65)

    # Log time since last post
    time_since = get_time_since_last_post()
    if time_since is not None:
        logger.info("⏱️ Time elapsed since previous post: %.1f hours", time_since)

    chosen_topic = forced_topic
    chosen_category = "AI & CODING"
    chosen_hook = ""

    if chosen_topic:
        logger.info("⚡ Trend-Velocity / Forced Topic detected: \"%s\"", chosen_topic)
        logger.info("⚡ Bypassing manual review for trend-velocity / forced topic post. Publishing immediately!")
        if queue_for_approval:
            logger.info("⚡ Overriding queue_for_approval=False for urgent breaking trend post.")
            queue_for_approval = False

    # --------------------------------------------------------------------------
    # 1. Topic Discovery via 4 Core Feeds & 5-Stage Funnel
    # --------------------------------------------------------------------------
    if not chosen_topic:
        logger.info("[1/5] Harvesting live trends across 4 feeds (geo=%s)...", geo)
        feeds = fetch_all_feeds(geo=geo, max_per_feed=15)
        raw_items = []
        for src, items in feeds.items():
            raw_items.extend(items)
        logger.info("  ✓ Gathered %d raw headlines across Google Trends, TechCrunch, VentureBeat, and HN", len(raw_items))

        logger.info("[2/5] Filtering candidates through 5-Stage AI Funnel (with 15-post & 24h dedup)...")
        funnel_res = run_filtering_funnel(raw_items)
        sc = funnel_res.get("stage_counts", {})
        logger.info(
            "  ✓ Funnel Dropoff: Raw(%d) -> Clean(%d) -> Niche(%d) -> LLM(%d) -> Dedup(%d) -> Winners(%d)",
            sc.get("raw", 0),
            sc.get("stage1_blacklist", 0),
            sc.get("stage2_niche", 0),
            sc.get("stage3_semantic", 0),
            sc.get("stage4_dedup", 0),
            sc.get("stage5_actionable", 0),
        )

        winners = funnel_res.get("winning_topics", [])
        if not winners:
            logger.warning("No winner passed all 5 stages in this batch. Falling back to top niche candidate.")
            fallback = raw_items[0] if raw_items else {"title": "Essential Python AI Development Tools", "category": "AI & CODING"}
            chosen_topic = fallback.get("refined_title") or fallback.get("title")
            chosen_category = fallback.get("category", "AI & CODING")
        else:
            top_winner = winners[0]
            chosen_topic = top_winner.get("refined_title") or top_winner.get("title")
            chosen_category = top_winner.get("semantic_category") or top_winner.get("category", "AI & CODING")
            chosen_hook = top_winner.get("hook_angle", "")

    logger.info("🏆 SELECTED POST TOPIC: \"%s\" [Category: %s]", chosen_topic, chosen_category)

    # --------------------------------------------------------------------------
    # 2. Structured Content Planning with Groq & Playwright Rendering
    # --------------------------------------------------------------------------
    tmp_dir = Path(tempfile.mkdtemp(prefix="auto-social-"))

    if pipeline_mode == "photo":
        logger.info("[3/5] Planning single-image cheatsheet infographic with Groq...")
        content_plan = generate_cheatsheet_content(chosen_topic)
        series_name = content_plan.get("title", chosen_topic)
        logger.info("  ✓ Planned Infographic: \"%s\" with %d items", series_name, len(content_plan.get("items", [])))

        logger.info("[4/5] Rendering 2160x2700 Retina single photo via Playwright...")
        slide_path = render_infographic(content_plan, tmp_dir, image_format="jpeg")
        slide_paths = [slide_path]
        logger.info("  ✓ Rendered 1 single photo in %.2fs: %s (%d KB)", time.time() - start_time, slide_path.name, slide_path.stat().st_size // 1024)

    elif pipeline_mode == "flow":
        logger.info("[3/5] Planning 5-slide system architecture flowchart with Groq...")
        content_plan = generate_flow_carousel_content(chosen_topic)
        content_plan.setdefault("theme", "LIGHT")
        series_name = content_plan.get("series_title") or content_plan.get("cover_title", chosen_topic)
        logger.info("  ✓ Planned Flowchart Carousel: \"%s\" with %d slides", series_name, len(content_plan.get("slides", [])))

        logger.info("[4/5] Rendering 2160x2700 Retina slides via Playwright...")
        slide_paths = render_carousel_flow_slides(content_plan, tmp_dir, image_format="jpeg")
        logger.info("  ✓ Rendered %d flowchart slides in %.2fs", len(slide_paths), time.time() - start_time)
        for p in slide_paths:
            logger.info("    - %s (%d KB)", p.name, p.stat().st_size // 1024)

    else:  # listicle
        logger.info("[3/5] Planning 5-slide educational listicle with Groq...")
        content_plan = generate_carousel_content(chosen_topic)
        content_plan.setdefault("theme", "LIGHT")
        series_name = content_plan.get("series_title") or content_plan.get("cover_title", chosen_topic)
        logger.info("  ✓ Planned Listicle Carousel: \"%s\" with %d slides", series_name, len(content_plan.get("slides", [])))

        logger.info("[4/5] Rendering 2160x2700 Retina slides via Playwright...")
        slide_paths = render_listicle_slides(content_plan, tmp_dir, image_format="jpeg")
        logger.info("  ✓ Rendered %d listicle slides in %.2fs", len(slide_paths), time.time() - start_time)
        for p in slide_paths:
            logger.info("    - %s (%d KB)", p.name, p.stat().st_size // 1024)

    # --------------------------------------------------------------------------
    # 2.5 Visual Quality Gate & Composition Audit (4-Layer QA Engine)
    # --------------------------------------------------------------------------
    logger.info("[4.5/5] Auditing visual composition & layout safety with 4-Layer QA Engine...")

    # Layer 5: Auto-Recovery Loop for slide carousels
    if pipeline_mode in ("listicle", "flow") and "slides" in content_plan:
        from core.media_generator import verify_compiled_slides_vision, shorten_slide_text
        for recovery_pass in range(1, 3):
            is_approved, failed_indices = verify_compiled_slides_vision(slide_paths, is_listicle=True)
            if is_approved:
                logger.info("  ✓ AI Visual Layout Auditor: APPROVED all %d slide layouts.", len(slide_paths))
                break
            else:
                logger.warning("  ⚠️ AI Visual Layout Auditor: REJECTED slides at indices %s. Attempting recovery pass %d...", failed_indices, recovery_pass)
                if recovery_pass < 2:
                    for f_idx in failed_indices:
                        s_idx = f_idx - 1
                        if 0 <= s_idx < len(content_plan["slides"]):
                            s_data = content_plan["slides"][s_idx]
                            orig_desc = s_data.get("description", "")
                            s_data["description"] = shorten_slide_text(orig_desc)
                            logger.info("    Shortened text on slide %d to eliminate card overflow.", f_idx)
                    # Re-render with shortened descriptions
                    if pipeline_mode == "flow":
                        slide_paths = render_carousel_flow_slides(content_plan, tmp_dir, image_format="jpeg")
                    else:
                        slide_paths = render_listicle_slides(content_plan, tmp_dir, image_format="jpeg")

    audit_result = audit_slide_images(slide_paths, content_plan)
    if not audit_result.get("passed", True):
        err_msg = f"Visual Quality Gate Failed ({audit_result.get('score')}/10): {audit_result.get('issues')}"
        logger.error("❌ %s", err_msg)
        if not dry_run:
            raise RuntimeError(err_msg)
    else:
        logger.info("  ✓ Visual Quality Gate PASSED: Score %.1f/10 [%s]", audit_result.get("score"), audit_result.get("method"))

    # Record to local memory & Supabase PostgreSQL
    record_post(
        title=series_name,
        category=content_plan.get("category", chosen_category),
        hook=content_plan.get("hook_line") or chosen_hook,
    )

    # --------------------------------------------------------------------------
    # 3. Live Cloudinary Hosting & Instagram Publishing
    # --------------------------------------------------------------------------
    if dry_run:
        logger.info("⚠️ DRY-RUN MODE: Skipping Cloudinary upload and Instagram publishing.")
        result = {
            "status": "dry_run_complete",
            "topic": chosen_topic,
            "slot": active_slot,
            "format": pipeline_mode,
            "weekday": day_name,
            "series_title": series_name,
            "slides_rendered": len(slide_paths),
            "vision_score": audit_result.get("score"),
            "vision_method": audit_result.get("method"),
            "elapsed_seconds": round(time.time() - start_time, 2),
        }
        logger.info("✨ DRY RUN FINISHED SUCCESSFULLY in %.2fs", result["elapsed_seconds"])
        return result

    logger.info("[5/5] Uploading media to Cloudinary & publishing live to Instagram...")
    cloudinary_urls = upload_images_to_cloudinary(slide_paths)
    logger.info("  📝 Generating 3-stage audited Instagram caption with niche hashtags & disclaimer...")
    caption = generate_post_caption(
        topic=series_name,
        content_plan=content_plan,
        format_type=pipeline_mode,
    )
    from core.text_auditor import verify_text_content
    cap_audit = verify_text_content(series_name, caption)
    logger.info("  ✓ Generated caption (%d chars) | Compliance QA: %s (Caption OK: %s, Facts OK: %s)", len(caption), cap_audit.get('status'), cap_audit.get('caption_ok'), cap_audit.get('facts_ok'))

    logger.info("  💬 Generating engagement-driving auto-comment (first comment)...")
    auto_comment = generate_post_comment(
        topic=series_name,
        content_plan=content_plan,
        format_type=pipeline_mode,
    )
    logger.info("  ✓ Generated auto-comment: %s", auto_comment)

    # If Human Approval mode is enabled, place into 30-min approval queue
    if queue_for_approval:
        queued_item = queue_post_for_approval(
            topic=series_name,
            format_type=pipeline_mode,
            slot=active_slot,
            slide_paths=slide_paths,
            caption=caption,
            auto_comment=auto_comment,
            content_plan=content_plan,
            vision_score=audit_result.get("score", 10.0),
            vision_method=audit_result.get("method", "pil_retina_analyzer"),
            timeout_minutes=timeout_minutes,
            upload_cdn_now=True,
        )
        elapsed = round(time.time() - start_time, 2)
        logger.info("=" * 65)
        logger.info("⏱️ POST QUEUED FOR HUMAN APPROVAL! ID: %s (%dm timer) in %.2fs", queued_item['id'], timeout_minutes, elapsed)
        logger.info("Review & approve in Streamlit dashboard or let it auto-publish.")
        logger.info("=" * 65)

        # Sync full queued payload to Supabase & memory
        record_post(
            title=series_name,
            category=content_plan.get("category", chosen_category),
            hook=content_plan.get("hook_line") or chosen_hook,
            post_id=queued_item["id"],
            format_type=pipeline_mode,
            slide_urls=queued_item.get("image_urls", []),
            caption=caption,
            auto_comment=auto_comment,
            metadata={
                "status": "queued_for_approval",
                "queue_id": queued_item["id"],
                "expires_at": queued_item["expires_at"],
                "slot": active_slot,
                "weekday": day_name,
                "vision_score": audit_result.get("score"),
            },
        )

        return {
            "status": "queued_for_approval",
            "queue_id": queued_item["id"],
            "expires_at": queued_item["expires_at"],
            "timeout_minutes": timeout_minutes,
            "topic": chosen_topic,
            "slot": active_slot,
            "format": pipeline_mode,
            "weekday": day_name,
            "series_title": series_name,
            "image_urls": queued_item.get("image_urls", []),
            "elapsed_seconds": elapsed,
        }

    if pipeline_mode == "photo":
        logger.info("📸 Publishing Single Photo to Instagram (@vmatrix.co)...")
        ig_result = publish_to_instagram_photo(cloudinary_urls[0], caption, auto_comment=auto_comment)
    else:
        logger.info("🎨 Publishing %d-Slide Carousel to Instagram (@vmatrix.co)...", len(cloudinary_urls))
        ig_result = publish_to_instagram_carousel(cloudinary_urls, caption, auto_comment=auto_comment)

    post_id = ig_result.get("post_id", "unknown")
    comment_id = ig_result.get("comment_id")
    elapsed = round(time.time() - start_time, 2)

    # Persist complete published post to Supabase and local vector memory
    record_post(
        title=series_name,
        category=content_plan.get("category", chosen_category),
        hook=content_plan.get("hook_line") or chosen_hook,
        post_id=post_id,
        format_type=pipeline_mode,
        slide_urls=cloudinary_urls,
        caption=caption,
        auto_comment=auto_comment,
        metadata={
            "status": "published",
            "slot": active_slot,
            "weekday": day_name,
            "vision_score": audit_result.get("score"),
            "comment_id": comment_id,
        },
    )

    logger.info("=" * 65)
    logger.info("🎉 POST PUBLISHED LIVE ON INSTAGRAM! Post ID: %s | Comment ID: %s in %.2fs", post_id, comment_id or "N/A", elapsed)
    logger.info("=" * 65)

    return {
        "status": "published",
        "post_id": post_id,
        "comment_id": comment_id,
        "auto_comment": auto_comment,
        "topic": chosen_topic,
        "slot": active_slot,
        "format": pipeline_mode,
        "weekday": day_name,
        "series_title": series_name,
        "image_urls": cloudinary_urls,
        "elapsed_seconds": elapsed,
    }



def main():
    parser = argparse.ArgumentParser(description="Autonomous Social Engine Publisher")
    parser.add_argument(
        "--slot",
        type=str,
        choices=["auto", "morning", "evening"],
        default="auto",
        help="Publishing slot: 'morning' (Single Photo) or 'evening' (Rotated Carousel)",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["auto", "photo", "listicle", "flow"],
        default="auto",
        help="Format override: 'photo' (single infographic), 'listicle', or 'flow'",
    )
    parser.add_argument("--dry-run", action="store_true", help="Run full pipeline without publishing to Instagram")
    parser.add_argument("--topic", type=str, default=None, help="Force a specific topic instead of radar discovery")
    parser.add_argument("--force-topic", type=str, default=None, help="Alias for --topic: immediately publishes emergency trend breakthrough")
    parser.add_argument("--geo", type=str, default="IN", help="Trends region (IN or US)")
    parser.add_argument(
        "--queue-for-approval",
        action="store_true",
        help="Queue post into 30-minute human approval queue instead of publishing directly",
    )
    parser.add_argument(
        "--timeout-minutes",
        type=int,
        default=30,
        help="Approval grace period duration in minutes before auto-publishing (default: 30)",
    )
    parser.add_argument(
        "--audit-insights",
        action="store_true",
        help="Audit recent posts, query Meta Graph API insights, and update Supabase & vector memory",
    )

    args = parser.parse_args()

    if args.audit_insights:
        logger.info("🔍 Running on-demand Post-Publishing Analytics Audit via Graph API & Supabase...")
        audit_res = audit_published_posts_insights()
        print("\n" + "=" * 60)
        print("📈 POST-PUBLISHING ANALYTICS AUDIT SUMMARY")
        print("=" * 60)
        print(f"  Audited Posts: {audit_res.get('audited_count', 0)}")
        print(f"  Top Performers Identified: {audit_res.get('top_performers_count', 0)}")
        print(f"  Timestamp: {audit_res.get('timestamp')}")
        print("\n🏆 Top Performing Topics Active in Funnel Feedback Loop:")
        for tp in audit_res.get("top_performers", [])[:5]:
            m = tp.get("metrics", {})
            print(f"  - \"{tp['title']}\"")
            print(f"    Engagement Score: {tp['score']} (Saves: {m.get('saved', 0)}, Shares: {m.get('shares', 0)}, Reach: {m.get('reach', 0)})")
        print("=" * 60)
        return

    effective_topic = args.force_topic or args.topic

    res = run_autonomous_post(
        dry_run=args.dry_run,
        forced_topic=effective_topic,
        slot=args.slot,
        format_override=args.format,
        geo=args.geo,
        queue_for_approval=args.queue_for_approval,
        timeout_minutes=args.timeout_minutes,
    )
    print("\nEXECUTION SUMMARY:")
    for k, v in res.items():
        if k != "image_urls":
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
