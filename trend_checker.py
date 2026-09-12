"""
trend_checker.py
----------------
Automated Hourly Trend Velocity Watchdog for Vmatrix Social OS.
Runs every 60 minutes to monitor real-time search spikes on Google Trends:
1. Harvests live search spikes from Google Trends (US & India feeds).
2. Filters against 24-hour post history to prevent duplicate coverage.
3. Passes candidates through Groq Secondary Brain (openai/gpt-oss-120b / llama-3.3-70b)
   to filter non-tech noise and detect explosive breakthroughs (AI, Dev, Architecture, Fintech).
4. If a spiked trend is detected (urgency score >= 7/10):
   - Sends a rich Discord embed notification via webhook.
   - Dispatches a GitHub Actions repository_dispatch event ('trend_velocity_post')
     to immediately bypass the normal schedule and publish a 4K Carousel to Instagram.
"""

import os
import sys
import time
import json
import argparse
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from dotenv import load_dotenv

# Ensure stdout handles UTF-8 on Windows and Linux runners
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv()

from core.feeds import fetch_google_trends
from core.memory import get_recent_posts
from core.llm_utils import call_secondary_brain
from core.utils import logger


DEFAULT_REPO = "theayushagarwal/vmatrix"


def get_github_repo() -> str:
    """Resolves repo slug from environment or git config."""
    return os.environ.get("GITHUB_REPOSITORY") or DEFAULT_REPO


def evaluate_trend_velocity(candidates: List[Dict[str, Any]], recent_titles: List[str]) -> Optional[Dict[str, Any]]:
    """
    Evaluates candidate trends using Groq Secondary Brain.
    Filters out non-tech noise and identifies explosive breakthroughs.
    """
    if not candidates:
        logger.info("No candidates provided for trend velocity evaluation.")
        return None

    # Filter out topics covered in the past 24 hours
    recent_titles_lower = [t.lower() for t in recent_titles]
    unseen_candidates = []
    for c in candidates:
        title = c.get("title", "").strip()
        if not title:
            continue
        # Check if topic or close match was published recently
        if any(recent in title.lower() or title.lower() in recent for recent in recent_titles_lower):
            logger.info("  Skipping recent duplicate: '%s'", title)
            continue
        unseen_candidates.append(c)

    if not unseen_candidates:
        logger.info("All candidates have been covered within the last 24 hours.")
        return None

    logger.info("Evaluating %d candidate trends with Groq Secondary Brain...", len(unseen_candidates))

    prompt = f"""
You are the Chief Trend Velocity Intelligence Officer for @vmatrix.co (premier Instagram page on AI Engineering, Developer Tools, System Architecture, and Tech Finance).

Analyze this list of real-time search trends from Google Trends:
{json.dumps(unseen_candidates, indent=2)}

YOUR MISSION:
1. STRICT FILTER: Discard entertainment, sports, celebrity gossip, mainstream politics, movies, and non-tech events.
2. DETECT VELOCITY: Is there a breakthrough AI model, major tech framework update, dev tool launch, severe cyber incident, or high-impact tech finance event experiencing an explosive search spike?
3. SELECT THE WINNER: If an explosive topic exists with high developer relevance, select the #1 winner.
4. URGENCY SCORE (1-10): Rate 1-10 on whether we must immediately publish an emergency carousel right now. (Score >= 7 triggers emergency auto-publish).

You must output ONLY valid JSON matching this exact structure:
{{
  "spike_detected": true,
  "winning_trend": "Refined Topic Title Suitable for a 5-Slide Instagram Carousel",
  "category": "AI & CODING",
  "search_volume": "50K+ searches",
  "urgency_score": 8,
  "reasoning": "Short 1-2 sentence explanation of why this is exploding and why developers care."
}}

If NO tech/AI breakthrough is spiking, output:
{{
  "spike_detected": false,
  "winning_trend": null,
  "category": null,
  "search_volume": null,
  "urgency_score": 2,
  "reasoning": "No relevant AI or dev breakthroughs currently spiking."
}}
"""

    response_text = call_secondary_brain(prompt, temperature=0.1, response_mime_type="application/json")
    if not response_text:
        logger.warning("Groq Secondary Brain did not return a response for trend evaluation.")
        return None

    try:
        # Clean any accidental markdown code blocks
        clean_json = response_text.strip()
        if clean_json.startswith("```"):
            clean_json = clean_json.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        data = json.loads(clean_json)
        return data
    except Exception as e:
        logger.warning("Failed to parse JSON response from trend evaluation: %s (Raw: %s)", e, response_text[:200])
        return None


def send_discord_alert(webhook_url: str, trend_info: Dict[str, Any], triggered_dispatch: bool) -> bool:
    """Sends a rich Discord embed notification when a velocity spike is detected."""
    if not webhook_url:
        logger.info("No DISCORD_WEBHOOK_URL configured, skipping Discord notification.")
        return False

    status_text = "⚡ Instant 4K Carousel Dispatch Triggered!" if triggered_dispatch else "👀 Monitored (Dry Run / Test Mode)"
    urgency = trend_info.get("urgency_score", 7)
    color = 0xFF4500 if urgency >= 8 else 0x00FF7F  # Orange-Red or Spring Green

    embed = {
        "title": "🚨 BREAKING AI TREND VELOCITY SPIKE DETECTED",
        "description": f"**Topic:** {trend_info.get('winning_trend')}\n\n{trend_info.get('reasoning', '')}",
        "color": color,
        "fields": [
            {"name": "🔥 Search Volume", "value": str(trend_info.get("search_volume") or "Trending Spike"), "inline": True},
            {"name": "⚡ Urgency Score", "value": f"{urgency}/10", "inline": True},
            {"name": "📂 Category", "value": str(trend_info.get("category") or "AI & CODING"), "inline": True},
            {"name": "🚀 Pipeline Action", "value": status_text, "inline": False},
        ],
        "footer": {"text": f"Vmatrix Hourly Trend Velocity Watchdog • {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"},
    }

    payload = {
        "username": "Vmatrix Trend Velocity Watchdog",
        "avatar_url": "https://raw.githubusercontent.com/theayushagarwal/vmatrix/main/dashboard/static/logo.png",
        "embeds": [embed],
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code in (200, 204):
            logger.info("✓ Successfully delivered Discord webhook alert.")
            return True
        else:
            logger.warning("Discord webhook returned status %d: %s", resp.status_code, resp.text)
    except Exception as e:
        logger.warning("Error sending Discord webhook alert: %s", e)
    return False


def trigger_github_dispatch(trend_title: str, payload_extra: Optional[Dict[str, Any]] = None) -> bool:
    """
    Triggers GitHub Actions workflow via repository_dispatch event 'trend_velocity_post'.
    This automatically wakes up auto_publish.yml with the forced topic.
    """
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_PAT_FOR_SECRETS")
    if not token:
        logger.error("❌ Cannot trigger GitHub repository_dispatch: GH_TOKEN or GITHUB_TOKEN not configured.")
        return False

    repo = get_github_repo()
    url = f"https://api.github.com/repos/{repo}/dispatches"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    client_payload = {"trend": trend_title}
    if payload_extra:
        client_payload.update(payload_extra)

    payload = {
        "event_type": "trend_velocity_post",
        "client_payload": client_payload,
    }

    try:
        logger.info("Triggering GitHub repository_dispatch for repo '%s' with trend '%s'...", repo, trend_title)
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code == 204:
            logger.info("🎉 SUCCESS: GitHub Actions repository_dispatch 'trend_velocity_post' triggered successfully!")
            return True
        else:
            logger.error("Failed to trigger repository_dispatch: HTTP %d - %s", resp.status_code, resp.text)
            return False
    except Exception as e:
        logger.error("Error connecting to GitHub REST API: %s", e)
        return False


def run_trend_check(dry_run: bool = False, force_publish: bool = False) -> Dict[str, Any]:
    """
    Executes a single trend velocity check:
    1. Fetches trends from US & IN.
    2. Gathers recent 24h post history.
    3. Evaluates with Groq Secondary Brain.
    4. Triggers alert & GitHub dispatch if spiked trend detected.
    """
    start_time = time.time()
    logger.info("=" * 65)
    logger.info("⚡ HOURLY TREND VELOCITY WATCHDOG SCAN STARTED")
    logger.info("🕒 Time: %s", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))
    logger.info("=" * 65)

    # 1. Harvest Google Trends across key geos
    candidates = []
    for geo in ["US", "IN"]:
        try:
            trends = fetch_google_trends(geo=geo, max_items=12)
            candidates.extend(trends)
            logger.info("  Fetched %d Google Trends items for geo=%s", len(trends), geo)
        except Exception as e:
            logger.warning("Failed fetching Google Trends for geo=%s: %s", geo, e)

    # 2. Retrieve recent posts to guard against duplicates
    recent_posts = get_recent_posts(days=1)
    recent_titles = [p.get("title", "") for p in recent_posts if p.get("title")]
    logger.info("  Found %d posts published in the last 24 hours for deduplication check.", len(recent_titles))

    # 3. Evaluate with Groq Secondary Brain
    evaluation = evaluate_trend_velocity(candidates, recent_titles)

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.time() - start_time, 2),
        "candidates_count": len(candidates),
        "evaluation": evaluation,
        "action_taken": "none",
    }

    if not evaluation or not evaluation.get("spike_detected"):
        logger.info("ℹ️ No spiked tech/AI trends detected in this cycle. Watchdog standing by.")
        result["action_taken"] = "no_spike_detected"
        return result

    winning_trend = evaluation.get("winning_trend")
    urgency_score = evaluation.get("urgency_score", 0)
    logger.info("🔥 BREAKTHROUGH DETECTED: '%s' (Urgency: %d/10)", winning_trend, urgency_score)
    logger.info("   Reasoning: %s", evaluation.get("reasoning"))

    should_trigger = force_publish or (urgency_score >= 7)

    if not should_trigger:
        logger.info("Trend urgency score (%d/10) below threshold (7). No auto-publish triggered.", urgency_score)
        result["action_taken"] = "below_threshold"
        return result

    if dry_run:
        logger.info("⚠️ DRY-RUN MODE: Would dispatch GitHub Actions event for '%s'. Skipping API call.", winning_trend)
        result["action_taken"] = "dry_run_simulated"
        send_discord_alert(os.environ.get("DISCORD_WEBHOOK_URL", ""), evaluation, triggered_dispatch=False)
        return result

    # 4. Trigger GitHub dispatch & Discord alert
    dispatch_success = trigger_github_dispatch(winning_trend, payload_extra={
        "urgency_score": urgency_score,
        "reasoning": evaluation.get("reasoning", ""),
        "category": evaluation.get("category", "AI & CODING"),
    })

    result["action_taken"] = "dispatched" if dispatch_success else "dispatch_failed"
    result["dispatch_success"] = dispatch_success

    # Send Discord notification
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    send_discord_alert(webhook_url, evaluation, triggered_dispatch=dispatch_success)

    logger.info("=" * 65)
    logger.info("✅ WATCHDOG CYCLE COMPLETED in %.2fs. Action: %s", result["elapsed_seconds"], result["action_taken"])
    logger.info("=" * 65)

    return result


def main():
    parser = argparse.ArgumentParser(description="Google Trends Hourly Velocity Watchdog")
    parser.add_argument("--once", action="store_true", help="Run a single check and exit")
    parser.add_argument("--daemon", action="store_true", help="Run continuously in a loop")
    parser.add_argument("--interval", type=int, default=3600, help="Check interval in seconds (default: 3600s / 60m)")
    parser.add_argument("--dry-run", action="store_true", help="Scan and evaluate without triggering external actions")
    parser.add_argument("--force-publish", action="store_true", help="Trigger dispatch regardless of urgency threshold")

    args = parser.parse_args()

    if args.daemon:
        logger.info("🚀 Starting Trend Velocity Watchdog Daemon (Interval: %d seconds / %d minutes)", args.interval, args.interval // 60)
        while True:
            try:
                run_trend_check(dry_run=args.dry_run, force_publish=args.force_publish)
            except Exception as e:
                logger.error("Unexpected error in watchdog cycle: %s", e)
            logger.info("Sleeping for %d seconds until next scan...", args.interval)
            time.sleep(args.interval)
    else:
        run_trend_check(dry_run=args.dry_run, force_publish=args.force_publish)


if __name__ == "__main__":
    main()
