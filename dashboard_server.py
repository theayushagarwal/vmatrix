"""
dashboard_server.py
-------------------
Vmatrix Social OS · Standalone High-Performance Web Dashboard
Runs 100% locally WITHOUT Streamlit!

Features:
- Live RSS / Google Trends / TechCrunch radar
- 5-Stage Mathematical Funnel
- 4K Retina Carousel Generator & Viewer (2160x2700 pure white)
- 30-Minute Human Approval Queue with live countdown
- Competitor Outlier Spy with 3-Gate Math & Groq Virality Reverse-Engineering
- Direct Instagram Publishing & Supabase telemetry
"""

import os
import sys
import time
import shutil
import webbrowser
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv

# Ensure stdout handles UTF-8 on Windows
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
    render_listicle_slides,
    render_carousel_flow_slides,
    publish_to_instagram_carousel,
    publish_to_instagram_photo,
    queue_post_for_approval,
    load_approval_queue,
    get_pending_approvals,
    get_time_remaining,
    extend_approval_timeout,
    approve_and_publish_post,
    reject_queued_post,
    process_auto_publish_timeouts,
    fetch_posts_from_supabase,
    get_recent_posts,
    record_post,
    generate_post_caption,
    generate_post_comment,
    InstaScraper,
    analyze_post_virality,
    detect_viral_outliers,
    db,
)
from core.utils import logger

app = FastAPI(title="Vmatrix Social OS Dashboard", version="2.5")

ROOT_DIR = Path(__file__).resolve().parent
SLIDES_OUTPUT_DIR = ROOT_DIR / "output_slides"
SLIDES_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

QUEUE_MEDIA_DIR = ROOT_DIR / "data" / "queue_media"
QUEUE_MEDIA_DIR.mkdir(parents=True, exist_ok=True)

DASHBOARD_DIR = ROOT_DIR / "dashboard"
DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)

# Static file mounts
app.mount("/slides", StaticFiles(directory=str(SLIDES_OUTPUT_DIR)), name="slides")
app.mount("/queue_media", StaticFiles(directory=str(QUEUE_MEDIA_DIR)), name="queue_media")


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------
class FunnelRequest(BaseModel):
    geo: str = "IN"


class GenerateRequest(BaseModel):
    topic: str
    mode: str = "listicle"  # 'listicle' or 'flow'
    image_format: str = "jpeg"


class EnqueueRequest(BaseModel):
    topic: str
    format_type: str = "carousel"
    slot: str = "on_demand"
    slide_paths: List[str]
    caption: str = ""
    auto_comment: str = ""
    timeout_minutes: int = 30


class PublishDirectRequest(BaseModel):
    slide_paths: List[str]
    caption: str
    auto_comment: str = ""


class CompetitorScrapeRequest(BaseModel):
    handle: str
    niche: str = "AI & CODING"
    limit: int = 6
    force: bool = False


class OutlierFilterRequest(BaseModel):
    posts: List[Dict[str, Any]]
    multiplier_threshold: float = 1.5
    min_cohort_size: int = 2


class AnalyzePostRequest(BaseModel):
    post_data: Dict[str, Any]


class VelocityCheckRequest(BaseModel):
    dry_run: bool = False
    force_publish: bool = False


# In-memory record of the last velocity check
LAST_VELOCITY_CHECK = {
    "status": "idle",
    "timestamp": None,
    "result": None,
}


# ---------------------------------------------------------------------------
# API Routes: Telemetry & Status
# ---------------------------------------------------------------------------
@app.get("/api/status")
def get_system_status():
    recent = get_recent_posts(days=30)
    pending_queue = get_pending_approvals()
    competitor_posts = db.get_competitor_posts(limit=100)

    return {
        "status": "online",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "telemetry": {
            "groq": bool(os.environ.get("GROQ_API_KEY")),
            "apify": bool(os.environ.get("APIFY_API_KEY") or os.environ.get("APIFY_API_TOKEN")),
            "supabase": bool(os.environ.get("SUPABASE_URL") and (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY"))),
            "openrouter": bool(os.environ.get("OPENROUTER_API_KEY")),
            "huggingface": bool(os.environ.get("HUGGINGFACE_API_KEY") or os.environ.get("HF_TOKEN")),
            "cloudinary": bool(os.environ.get("CLOUDINARY_CLOUD_NAME") and os.environ.get("CLOUDINARY_API_KEY")),
            "instagram": bool(os.environ.get("IG_USER_ID") and os.environ.get("IG_ACCESS_TOKEN")),
            "logodev": bool(os.environ.get("LOGODEV_PUBLISHABLE_KEY") or os.environ.get("LOGODEV_SECRET_KEY")),
            "brandfetch": bool(os.environ.get("BRANDFETCH_API_KEY")),
        },
        "stats": {
            "memory_post_count": len(recent),
            "pending_queue_count": len(pending_queue),
            "competitor_post_count": len(competitor_posts),
        }
    }


# ---------------------------------------------------------------------------
# API Routes: Live Feeds & Funnel
# ---------------------------------------------------------------------------
@app.get("/api/feeds")
def get_live_feeds(geo: str = "IN"):
    try:
        feeds = fetch_all_feeds(geo=geo, max_per_feed=10)
        total_items = sum(len(items) for items in feeds.values())
        return {"success": True, "feeds": feeds, "total_count": total_items}
    except Exception as e:
        logger.error(f"Failed to fetch feeds: {e}")
        return {"success": False, "error": str(e), "feeds": {}}


@app.post("/api/funnel")
def run_funnel_endpoint(req: FunnelRequest):
    try:
        all_raw = fetch_all_feeds(geo=req.geo, max_per_feed=15)
        combined = []
        for f, items in all_raw.items():
            combined.extend(items)

        if not combined:
            return {"success": False, "error": "No raw trend items fetched from providers."}

        results = run_filtering_funnel(combined)
        return {"success": True, "results": results}
    except Exception as e:
        logger.error(f"Funnel execution error: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/trends/velocity-check")
def run_velocity_check_endpoint(req: VelocityCheckRequest = VelocityCheckRequest()):
    """
    Triggers an on-demand Google Trends Velocity Watchdog cycle.
    Evaluates real-time search spikes with Groq Secondary Brain.
    """
    try:
        from trend_checker import run_trend_check
        res = run_trend_check(dry_run=req.dry_run, force_publish=req.force_publish)
        global LAST_VELOCITY_CHECK
        LAST_VELOCITY_CHECK = {
            "status": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "result": res,
        }
        return {"success": True, "data": res}
    except Exception as e:
        logger.error(f"Velocity check execution error: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/trends/velocity-status")
def get_velocity_status_endpoint():
    """Returns the most recent trend velocity check telemetry."""
    return {"success": True, "watchdog": LAST_VELOCITY_CHECK}


# ---------------------------------------------------------------------------
# API Routes: Content Generator & Slide Renderer
# ---------------------------------------------------------------------------
@app.post("/api/generate")
def generate_carousel_endpoint(req: GenerateRequest):
    try:
        logger.info(f"Generating 4K Carousel for '{req.topic}' (mode={req.mode})")
        if req.mode == "flow":
            content = generate_flow_carousel_content(req.topic)
            content.setdefault("theme", "LIGHT")
            paths = render_carousel_flow_slides(content, SLIDES_OUTPUT_DIR, image_format=req.image_format)
        else:
            content = generate_carousel_content(req.topic)
            content.setdefault("theme", "LIGHT")
            paths = render_listicle_slides(content, SLIDES_OUTPUT_DIR, image_format=req.image_format)

        title = content.get("series_title") or content.get("cover_title") or req.topic
        record_post(title=title, category=content.get("category", "AI & CODING"), hook=content.get("hook_line", ""))

        # Auto-generate crisp caption and comment
        caption = generate_post_caption(topic=req.topic, content_plan=content)
        auto_comment = generate_post_comment(topic=req.topic, content_plan=content)

        slide_urls = [f"/slides/{Path(p).name}" for p in paths]

        return {
            "success": True,
            "content": content,
            "slide_paths": [str(p) for p in paths],
            "slide_urls": slide_urls,
            "caption": caption,
            "auto_comment": auto_comment,
        }
    except Exception as e:
        logger.error(f"Generation error: {e}")
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# API Routes: 30-Minute Approval Queue
# ---------------------------------------------------------------------------
@app.get("/api/queue")
def get_approval_queue_endpoint():
    try:
        # Check auto-publish timeouts
        process_auto_publish_timeouts(auto_publish_enabled=True)
        pending = get_pending_approvals()
        formatted = []
        for p in pending:
            mins, secs, frac = get_time_remaining(p)
            slide_paths = p.get("slide_paths") or []
            
            # Form browser-accessible URLs for queue slides
            slide_urls = []
            for sp in slide_paths:
                p_obj = Path(sp)
                if p_obj.exists():
                    try:
                        rel = p_obj.relative_to(QUEUE_MEDIA_DIR)
                        slide_urls.append(f"/queue_media/{rel.as_posix()}")
                    except ValueError:
                        slide_urls.append(f"/slides/{p_obj.name}")
            
            # Fallback to image_urls if Cloudinary URLs exist
            if not slide_urls and p.get("image_urls"):
                slide_urls = p.get("image_urls")

            formatted.append({
                "id": p["id"],
                "topic": p.get("topic") or p.get("title", "Untitled Carousel"),
                "category": p.get("category", "AI & CODING"),
                "format": p.get("format", "carousel"),
                "caption": p.get("caption", ""),
                "auto_comment": p.get("auto_comment", ""),
                "slide_urls": slide_urls,
                "slide_paths": slide_paths,
                "mins_left": mins,
                "secs_left": secs,
                "status": p.get("status", "pending"),
                "created_at_iso": p.get("created_at_iso", ""),
            })
        return {"success": True, "pending": formatted}
    except Exception as e:
        logger.error(f"Queue error: {e}")
        return {"success": False, "error": str(e), "pending": []}


@app.post("/api/queue/enqueue")
def enqueue_post_endpoint(req: EnqueueRequest):
    try:
        p_paths = [Path(p) for p in req.slide_paths]
        existing = [p for p in p_paths if p.exists()]
        if not existing:
            return {"success": False, "error": "No valid slide files found to enqueue."}

        queued = queue_post_for_approval(
            topic=req.topic,
            format_type=req.format_type,
            slot=req.slot,
            slide_paths=existing,
            caption=req.caption,
            auto_comment=req.auto_comment,
            timeout_minutes=req.timeout_minutes,
            upload_cdn_now=bool(os.environ.get("CLOUDINARY_CLOUD_NAME")),
        )
        return {"success": True, "item": queued}
    except Exception as e:
        logger.error(f"Enqueue error: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/queue/{item_id}/approve")
def approve_queue_item(item_id: str):
    try:
        success = approve_and_publish_post(item_id)
        return {"success": success}
    except Exception as e:
        logger.error(f"Approve error: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/queue/{item_id}/reject")
def reject_queue_item(item_id: str):
    try:
        success = reject_queued_post(item_id)
        return {"success": success}
    except Exception as e:
        logger.error(f"Reject error: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/queue/{item_id}/extend")
def extend_queue_item(item_id: str):
    try:
        success = extend_approval_timeout(item_id, extra_minutes=15)
        return {"success": bool(success)}
    except Exception as e:
        logger.error(f"Extend error: {e}")
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# API Routes: Direct Instagram Publishing
# ---------------------------------------------------------------------------
@app.post("/api/publish")
def publish_direct_endpoint(req: PublishDirectRequest):
    try:
        paths = [Path(p) for p in req.slide_paths if Path(p).exists()]
        if not paths:
            return {"success": False, "error": "No valid slides provided for publishing."}

        # 1. Upload to Cloudinary
        image_urls = upload_images_to_cloudinary(paths)
        if not image_urls:
            return {"success": False, "error": "Failed to upload slides to CDN."}

        # 2. Publish to Instagram Graph API
        result = publish_to_instagram_carousel(
            image_urls=image_urls,
            caption=req.caption,
        )
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Direct publish error: {e}")
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# API Routes: Competitor Outlier Intelligence (Phase 2)
# ---------------------------------------------------------------------------
@app.post("/api/competitor/scrape")
def scrape_competitor_endpoint(req: CompetitorScrapeRequest):
    try:
        scraper = InstaScraper()
        clean_handle = req.handle.strip().lstrip("@")
        posts = scraper.scrape(
            handle=clean_handle,
            niche=req.niche,
            limit=req.limit,
            force=req.force,
        )
        return {"success": True, "posts": posts, "count": len(posts)}
    except Exception as e:
        logger.error(f"Scraper error: {e}")
        return {"success": False, "error": str(e), "posts": []}


@app.post("/api/competitor/outliers")
def detect_outliers_endpoint(req: OutlierFilterRequest):
    try:
        outlier_data = detect_viral_outliers(
            posts=req.posts,
            multiplier_threshold=req.multiplier_threshold,
            min_cohort_size=req.min_cohort_size,
        )
        return {"success": True, "data": outlier_data}
    except Exception as e:
        logger.error(f"Outlier detection error: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/competitor/analyze")
def analyze_competitor_post_endpoint(req: AnalyzePostRequest):
    try:
        analysis = analyze_post_virality(req.post_data)
        # Update in database if shortcode exists
        sc = req.post_data.get("shortcode")
        if sc and analysis:
            db.update_virality_analysis(sc, analysis)
        return {"success": True, "analysis": analysis}
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/competitor/posts")
def get_stored_competitor_posts(handle: Optional[str] = None, niche: Optional[str] = None, limit: int = 40):
    try:
        clean_handle = handle.strip().lstrip("@") if handle else None
        posts = db.get_competitor_posts(handle=clean_handle, niche=niche, limit=limit)
        return {"success": True, "posts": posts, "count": len(posts)}
    except Exception as e:
        logger.error(f"Get stored posts error: {e}")
        return {"success": False, "error": str(e), "posts": []}


# ---------------------------------------------------------------------------
# Frontend Single Page App Route
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    html_file = DASHBOARD_DIR / "index.html"
    if html_file.exists():
        return HTMLResponse(content=html_file.read_text(encoding="utf-8"))
    return HTMLResponse(
        content="<h1>Vmatrix Social OS</h1><p>Dashboard UI is compiling. Please refresh in a moment...</p>",
        status_code=200,
    )


def main():
    port = int(os.environ.get("PORT", 8000))
    print("\n" + "=" * 60)
    print("🚀 VMATRIX SOCIAL OS · FASTAPI DASHBOARD SERVER")
    print(f"🔗 Local Dashboard URL: http://localhost:{port}")
    print("⚡ 100% Non-Streamlit High-Performance Single-Page App")
    print("=" * 60 + "\n")
    
    # Auto-open browser
    try:
        webbrowser.open(f"http://localhost:{port}")
    except Exception:
        pass
        
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
