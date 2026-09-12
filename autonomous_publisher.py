"""
autonomous_publisher.py
-----------------------
Fully autonomous pipeline runner designed for GitHub Actions and cron jobs:
1. Harvests live signals from 4 data feeds (Google Trends, TechCrunch AI, VentureBeat AI, Hacker News).
2. Filters signals through the 5-Stage AI Funnel (Blacklist -> Niche Scorer -> Groq LLM -> Vector Memory -> Format Fit).
3. Selects the #1 highest-scoring winning topic.
4. Generates a structured 5-slide carousel using Groq (openai/gpt-oss-120b with failover).
5. Renders 2160x2700 Retina slides using batch in-memory Playwright (95% JPEG).
6. Uploads slides to Cloudinary.
7. Publishes directly to Instagram Live via Meta Graph API.
8. Syncs to Supabase cloud database & updates 30-day post history memory.
"""

import os
import sys
import argparse
import tempfile
import time
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
    generate_flow_carousel_content,
    render_carousel_slides,
    render_carousel_flow_slides,
    upload_images_to_cloudinary,
    publish_to_instagram_carousel,
    record_post,
)
from core.utils import logger


def run_autonomous_post(
    dry_run: bool = False,
    forced_topic: str | None = None,
    format_override: str = "auto",
    geo: str = "IN",
) -> dict:
    """
    Executes the full end-to-end autonomous publishing loop.
    Returns summary execution dictionary.
    """
    start_time = time.time()
    logger.info("=" * 60)
    logger.info("🚀 STARTING AUTONOMOUS PUBLISHING PIPELINE")
    logger.info("=" * 60)

    chosen_topic = forced_topic
    chosen_category = "AI & CODING"
    chosen_hook = ""
    pipeline_mode = format_override

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

        logger.info("[2/5] Filtering candidates through 5-Stage AI Funnel...")
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
            # Fallback to top-scoring item if available
            fallback = raw_items[0] if raw_items else {"title": "Essential Python AI Development Tools", "category": "AI & CODING"}
            chosen_topic = fallback.get("refined_title") or fallback.get("title")
            chosen_category = fallback.get("category", "AI & CODING")
        else:
            top_winner = winners[0]
            chosen_topic = top_winner.get("refined_title") or top_winner.get("title")
            chosen_category = top_winner.get("semantic_category") or top_winner.get("category", "AI & CODING")
            chosen_hook = top_winner.get("hook_angle", "")

    logger.info("🏆 SELECTED POST TOPIC: \"%s\" [Category: %s]", chosen_topic, chosen_category)

    # Determine format (Listicle vs Architecture Flowchart)
    if pipeline_mode == "auto":
        # Architecture flow if topic mentions pipeline, agent, architecture, backend, stack, or real-time
        t_lower = chosen_topic.lower()
        if any(w in t_lower for w in ("pipeline", "architecture", "agent", "flow", "stack", "backend", "system", "real-time", "realtime", "infra")):
            pipeline_mode = "flow"
        else:
            pipeline_mode = "listicle"

    logger.info("📐 SELECTED CAROUSEL FORMAT: %s", pipeline_mode.upper())

    # --------------------------------------------------------------------------
    # 2. Structured Content Planning with Groq
    # --------------------------------------------------------------------------
    logger.info("[3/5] Planning 5-slide structured carousel with Groq...")
    if pipeline_mode == "flow":
        content_plan = generate_flow_carousel_content(chosen_topic)
    else:
        content_plan = generate_carousel_content(chosen_topic)

    series_name = content_plan.get("series_title") or content_plan.get("cover_title", chosen_topic)
    logger.info("  ✓ Planned: \"%s\" with 5 slides", series_name)

    # --------------------------------------------------------------------------
    # 3. Batch In-Memory Slide Rendering (Playwright Retina 95% JPEG)
    # --------------------------------------------------------------------------
    logger.info("[4/5] Rendering 2160x2700 Retina slides via Playwright...")
    tmp_dir = Path(tempfile.mkdtemp(prefix="auto-social-"))
    if pipeline_mode == "flow":
        slide_paths = render_carousel_flow_slides(content_plan, tmp_dir, image_format="jpeg")
    else:
        slide_paths = render_carousel_slides(content_plan, tmp_dir, image_format="jpeg")

    logger.info("  ✓ Rendered %d slides in %.2fs", len(slide_paths), time.time() - start_time)
    for p in slide_paths:
        logger.info("    - %s (%d KB)", p.name, p.stat().st_size // 1024)

    # Record to local memory & Supabase PostgreSQL
    record_post(
        title=series_name,
        category=content_plan.get("category", chosen_category),
        hook=content_plan.get("hook_line") or chosen_hook,
    )

    # --------------------------------------------------------------------------
    # 4. Live Cloudinary Hosting & Instagram Publishing
    # --------------------------------------------------------------------------
    if dry_run:
        logger.info("⚠️ DRY-RUN MODE: Skipping Cloudinary upload and Instagram publishing.")
        result = {
            "status": "dry_run_complete",
            "topic": chosen_topic,
            "format": pipeline_mode,
            "series_title": series_name,
            "slides_rendered": len(slide_paths),
            "elapsed_seconds": round(time.time() - start_time, 2),
        }
        logger.info("✨ DRY RUN FINISHED SUCCESSFULLY in %.2fs", result["elapsed_seconds"])
        return result

    logger.info("[5/5] Uploading slides to Cloudinary & publishing to Instagram...")
    cloudinary_urls = upload_images_to_cloudinary(slide_paths)
    logger.info("  ✓ Uploaded %d slides to Cloudinary CDN", len(cloudinary_urls))

    caption = content_plan.get("caption", f"{series_name}\n\n#tech #coding #ai #programming #software")
    ig_result = publish_to_instagram_carousel(cloudinary_urls, caption)
    post_id = ig_result.get("post_id", "unknown")

    elapsed = round(time.time() - start_time, 2)
    logger.info("=" * 60)
    logger.info("🎉 POST PUBLISHED LIVE ON INSTAGRAM! Post ID: %s in %.2fs", post_id, elapsed)
    logger.info("=" * 60)

    return {
        "status": "published",
        "post_id": post_id,
        "topic": chosen_topic,
        "format": pipeline_mode,
        "series_title": series_name,
        "image_urls": cloudinary_urls,
        "elapsed_seconds": elapsed,
    }


def main():
    parser = argparse.ArgumentParser(description="Autonomous Social Engine Publisher")
    parser.add_argument("--dry-run", action="store_true", help="Run full pipeline without publishing to Instagram")
    parser.add_argument("--topic", type=str, default=None, help="Force a specific topic instead of radar discovery")
    parser.add_argument("--format", type=str, choices=["auto", "listicle", "flow"], default="auto", help="Carousel format")
    parser.add_argument("--geo", type=str, default="IN", help="Trends region (IN or US)")

    args = parser.parse_args()
    res = run_autonomous_post(
        dry_run=args.dry_run,
        forced_topic=args.topic,
        format_override=args.format,
        geo=args.geo,
    )
    print("\nEXECUTION SUMMARY:")
    for k, v in res.items():
        if k != "image_urls":
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
