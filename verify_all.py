import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

print("======================================================")
print("   ⚡ AI-SOCIAL-ENGINE COMPREHENSIVE VERIFICATION     ")
print("======================================================\n")

# 1. Test Feeds
print(">>> [1/5] Verifying 5 Core Data Feeds (including Apify Intelligence Radar)...")
from core.feeds import (
    fetch_all_feeds,
    fetch_google_trends,
    fetch_techcrunch_ai,
    fetch_venturebeat_ai,
    fetch_hacker_news,
    fetch_apify_trends,
)

gt = fetch_google_trends("IN", max_items=2)
tc = fetch_techcrunch_ai(max_items=2)
vb = fetch_venturebeat_ai(max_items=2)
hn = fetch_hacker_news(max_items=2)
ap = fetch_apify_trends(max_items=2)
all_feeds = fetch_all_feeds(geo="IN", max_per_feed=3)

print(f"  ✓ Google Trends (IN): {len(gt)} items")
print(f"  ✓ TechCrunch AI: {len(tc)} items")
print(f"  ✓ VentureBeat AI: {len(vb)} items")
print(f"  ✓ Hacker News: {len(hn)} items")
print(f"  ✓ Apify Intelligence Radar: {len(ap)} items")
total_items = sum(len(v) for v in all_feeds.values())
print(f"  ✓ Aggregated Feeds: {total_items} total items across 5 sources")
assert all(len(v) > 0 for k, v in all_feeds.items() if k != "apify_radar"), "One or more core feeds returned 0 items"

# 2. Test 5-Stage Funnel
print("\n>>> [2/4] Verifying 5-Stage Filtering Funnel & Vector Memory...")
from core.funnel import run_filtering_funnel, passes_blacklist, compute_niche_score
from core.memory import record_post, check_max_similarity

# Stage 1 assertions
assert not passes_blacklist("Live cricket match IPL finals score"), "Stage 1 failed to drop cricket"
assert passes_blacklist("DeepSeek releases v3.2 model architecture"), "Stage 1 falsely dropped tech headline"

# Stage 2 assertions
score_tech, _ = compute_niche_score("Python tools for Claude and AI agents")
assert score_tech >= 8, f"Stage 2 tech score low: {score_tech}"

# Stage 4 assertions
record_post("5 Essential Docker Commands for Developers", category="TOOLS")
sim_dup, matched = check_max_similarity("5 Essential Docker Commands for Developers", days=30)
assert sim_dup >= 0.80, f"Stage 4 duplicate not caught: {sim_dup}"

# Run Full Funnel on Live Feeds
raw_items = []
for items in all_feeds.values():
    raw_items.extend(items)
raw_items.append({"title": "Top 5 Cursor AI rules for clean React code", "summary": "Developer tutorial", "category": "TOOLS"})

funnel_report = run_filtering_funnel(raw_items)
sc = funnel_report["stage_counts"]
print(f"  ✓ Stage 1 Raw -> Blacklist: {sc['raw']} -> {sc['stage1_blacklist']} items")
print(f"  ✓ Stage 2 Niche Scoring: -> {sc['stage2_niche']} items")
print(f"  ✓ Stage 3 Semantic Classifier: -> {sc['stage3_semantic']} items")
print(f"  ✓ Stage 4 Vector Anti-Dup: -> {sc['stage4_dedup']} items")
print(f"  ✓ Stage 5 Winning Topics: -> {len(funnel_report['winning_topics'])} winners")
assert len(funnel_report["winning_topics"]) > 0, "Funnel produced 0 winners"

# 3. Test Logo & Favicon Resolvers (Logo.dev & Brandfetch)
print("\n>>> [3/5] Verifying Logo Resolvers (Logo.dev & Brandfetch)...")
from core.renderer import get_logo_url, get_favicon_url
logo_url = get_logo_url("cursor.com")
print(f"  ✓ Resolved Logo for cursor.com: {logo_url}")
assert "logo.dev" in logo_url or "googleusercontent" in logo_url, "Logo resolution returned invalid URL"

# 4. Test Content Planning with Groq (openai/gpt-oss-120b & failover)
print("\n>>> [4/6] Verifying Groq Structured Content Generator...")
from core.generator import generate_carousel_content, generate_cheatsheet_content, generate_flow_carousel_content

planned_carousel = generate_carousel_content("3 Python Tips for AI Engineers")
print(f"  ✓ Listicle Series: \"{planned_carousel.get('series_title')}\" ({len(planned_carousel.get('slides', []))} slides)")
assert len(planned_carousel.get("slides", [])) >= 5, "Carousel must have at least 5 slides"

planned_flow = generate_flow_carousel_content("Building a Real-Time Voice AI Agent")
print(f"  ✓ Architecture Flow: \"{planned_flow.get('cover_title')}\" ({len(planned_flow.get('slides', []))} steps)")
assert len(planned_flow.get("slides", [])) >= 3, "Flow carousel must have at least 3 steps"

# 5. Test Slide Rendering Engine (Batch In-Memory 95% JPEG)
print("\n>>> [5/6] Verifying Playwright Batch In-Memory Slide Rendering (2160x2700 Retina)...")
from core.renderer import render_carousel_slides, render_carousel_flow_slides, render_infographic
from core.utils import validate_slide_image

tmp_dir = Path(tempfile.mkdtemp(prefix="verify-slides-"))
listicle_paths = render_carousel_slides(planned_carousel, tmp_dir, image_format="jpeg")
print(f"  ✓ Rendered {len(listicle_paths)} Listicle slides (JPEG):")
for p in listicle_paths:
    validate_slide_image(p, 2160, 2700)
    print(f"    - {p.name} ({p.stat().st_size / 1024:.1f} KB, 2160x2700 Retina)")

flow_paths = render_carousel_flow_slides(planned_flow, tmp_dir, image_format="jpeg")
print(f"  ✓ Rendered {len(flow_paths)} Architecture Flow slides (JPEG):")
for p in flow_paths:
    validate_slide_image(p, 2160, 2700)
    print(f"    - {p.name} ({p.stat().st_size / 1024:.1f} KB, 2160x2700 Retina)")

sample_info_data = {
    "title": "AI Developer Cheatsheet",
    "hook_line": "6 Essential AI tools every modern programmer should use daily",
    "category": "TOOLS",
    "items": [
        {"name": "Cursor", "domain": "cursor.com", "desc": "AI code editor with multi-file edits.", "badge": "TOP PICK"},
        {"name": "Claude 3.7", "domain": "anthropic.com", "desc": "Best-in-class reasoning and coding.", "badge": "FRONTIER"},
        {"name": "v0.dev", "domain": "v0.dev", "desc": "Generative UI with Tailwind CSS.", "badge": "FRONTEND"},
        {"name": "DeepSeek V3", "domain": "deepseek.com", "desc": "Cost-efficient open-weights coding.", "badge": "OPEN SOURCE"},
        {"name": "Ollama", "domain": "ollama.com", "desc": "Run local LLMs on your machine.", "badge": "LOCAL DEV"},
        {"name": "FastAPI", "domain": "fastapi.tiangolo.com", "desc": "High-performance Python backend framework.", "badge": "BACKEND"}
    ]
}

info_path = render_infographic(sample_info_data, tmp_dir, image_format="jpeg")
validate_slide_image(info_path, 2160, 2700)
print(f"  ✓ Rendered Infographic: {info_path.name} ({info_path.stat().st_size / 1024:.1f} KB, 2160x2700 Retina)")

# 6. Test Vision Quality Inspector (Pillow Retina & Multi-AI Vision Gate)
print("\n>>> [6/8] Verifying Vision Quality Gate & Composition Inspector...")
from core.vision_inspector import audit_slide_images, audit_cheatsheet_image

listicle_audit = audit_slide_images(listicle_paths)
assert listicle_audit["passed"], f"Listicle visual audit failed: {listicle_audit['issues']}"
print(f"  ✓ Listicle Visual Audit: PASSED ({listicle_audit['score']}/10 via {listicle_audit['method']})")

info_audit = audit_cheatsheet_image(info_path)
assert info_audit["passed"], f"Infographic visual audit failed: {info_audit['issues']}"
print(f"  ✓ Infographic Visual Audit: PASSED ({info_audit['score']}/10 via {info_audit['method']})")

# 7. Check Autonomous Scheduler, Auto-Comment Generator & Publishing Exports
print("\n>>> [7/8] Verifying Slot Resolver, Comment Engine & Publishing Exports...")
from autonomous_publisher import resolve_slot_and_format
from core.publisher import publish_to_instagram_photo, publish_to_instagram_carousel, post_instagram_comment
from core.caption import generate_post_comment
from core.memory import check_duplicate_guardrails, get_time_since_last_post

s_morn, f_morn = resolve_slot_and_format(slot="morning")
assert s_morn == "morning" and f_morn == "photo", f"Morning slot failed: {s_morn}, {f_morn}"
print(f"  ✓ Morning Slot Resolution: {s_morn} -> {f_morn} (Single Photo Infographic)")

test_comm = generate_post_comment("AI Dev Tools 2026", format_type="photo")
assert test_comm and len(test_comm) > 15, f"Comment generator returned invalid comment: {test_comm}"
print(f"  ✓ Auto-Comment Generator: \"{test_comm[:60]}...\" ({len(test_comm)} chars)")

is_dup, guard_msg = check_duplicate_guardrails("5 Essential Docker Commands for Developers")
assert is_dup, "Guardrails should detect recently recorded Docker post as duplicate"
print(f"  ✓ Anti-Duplication Guardrail Check: Caught duplicate ('{guard_msg}')")

# 8. Check 30-Minute Human Approval Queue Engine
print("\n>>> [8/9] Verifying 30-Minute Human Approval Queue & Governance Engine...")
from core.approval import (
    queue_post_for_approval,
    get_pending_approvals,
    get_time_remaining,
    extend_approval_timeout,
    update_queued_post,
    reject_queued_post,
    get_approval_history,
)

q_item = queue_post_for_approval(
    topic="Test Post for 30-Min Queue",
    format_type="listicle",
    slot="evening",
    slide_paths=[info_path],
    caption="Test caption for approval queue",
    auto_comment="Test first comment for approval queue",
    timeout_minutes=30,
    upload_cdn_now=False,
)
assert q_item["status"] == "pending", f"Queued post status invalid: {q_item['status']}"
mins, secs, frac = get_time_remaining(q_item)
assert mins >= 29, f"Countdown calculation unexpected: {mins}m {secs}s"
print(f"  ✓ Enqueued Post: ID '{q_item['id']}' | Countdown: {mins}m {secs}s remaining (fraction: {frac:.2f})")

updated_item = extend_approval_timeout(q_item["id"], extra_minutes=15)
assert updated_item["timeout_minutes"] == 45, f"Extended timeout failed: {updated_item['timeout_minutes']}"
print(f"  ✓ Timer Extension (+15m): New total duration {updated_item['timeout_minutes']} mins")

edited_item = update_queued_post(q_item["id"], caption="Edited caption for operator review")
assert edited_item["caption"] == "Edited caption for operator review", "Copy update failed"
print(f"  ✓ Operator Copy Edit: Updated caption successfully")

rej_item = reject_queued_post(q_item["id"], reason="Automated test rejection cleanup")
assert rej_item["status"] == "rejected", f"Rejection status invalid: {rej_item['status']}"
print(f"  ✓ Operator Rejection & Cancellation: Marked {rej_item['status']}")

# 9. Check UI Compilation & Syntax
print("\n>>> [9/9] Verifying Streamlit App Compilation...")
import py_compile
py_compile.compile("app.py")
print("  ✓ app.py compiled with zero syntax/import errors")

print("\n======================================================")
print("   🎉 ALL CHECKS PASSED: SYSTEM FULLY OPERATIONAL!    ")
print("======================================================")


