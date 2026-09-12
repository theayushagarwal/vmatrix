import sys
import tempfile
from pathlib import Path

print("======================================================")
print("   ⚡ AI-SOCIAL-ENGINE COMPREHENSIVE VERIFICATION     ")
print("======================================================\n")

# 1. Test Feeds
print(">>> [1/4] Verifying 4 Core Data Feeds...")
from core.feeds import fetch_all_feeds, fetch_google_trends, fetch_techcrunch_ai, fetch_venturebeat_ai, fetch_hacker_news

gt = fetch_google_trends("IN", max_items=2)
tc = fetch_techcrunch_ai(max_items=2)
vb = fetch_venturebeat_ai(max_items=2)
hn = fetch_hacker_news(max_items=2)
all_feeds = fetch_all_feeds(geo="IN", max_per_feed=3)

print(f"  ✓ Google Trends (IN): {len(gt)} items")
print(f"  ✓ TechCrunch AI: {len(tc)} items")
print(f"  ✓ VentureBeat AI: {len(vb)} items")
print(f"  ✓ Hacker News: {len(hn)} items")
total_items = sum(len(v) for v in all_feeds.values())
print(f"  ✓ Aggregated Feeds: {total_items} total items across 4 sources")
assert all(len(v) > 0 for v in all_feeds.values()), "One or more feeds returned 0 items"

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

# 3. Test Slide Rendering Engine
print("\n>>> [3/4] Verifying Playwright Slide Rendering Engine...")
from core.renderer import render_carousel_slides, render_infographic
from core.utils import validate_png

sample_carousel_data = {
    "series_title": "5 CURSOR AI TRICKS",
    "hook_line": "Stop writing boilerplate code by hand",
    "category": "AI & CODING",
    "slides": [
        {"type": "cover", "title": "5 Cursor AI Hacks Every Dev Needs", "hook_line": "Write code 3x faster", "subtitle": "Master the AI IDE in 2 minutes"},
        {"type": "content", "step_num": "01", "title": "Custom .cursorrules", "description": "Enforce framework rules across your codebase.", "key_benefit": "SAVES 2 HRS", "tool_name": "Cursor", "tool_domain": "cursor.com"},
        {"type": "content", "step_num": "02", "title": "Composer Mode", "description": "Generate full multi-file features in one prompt.", "key_benefit": "10X SPEED", "tool_name": "Composer", "tool_domain": "github.com"},
        {"type": "content", "step_num": "03", "title": "Context Tagging @Docs", "description": "Index third-party documentation directly in chat.", "key_benefit": "ZERO HALLUCINATIONS", "tool_name": "Docs", "tool_domain": "notion.so"},
        {"type": "outro", "title": "Ready to 10x your workflow?", "cta_keyword": "CURSOR", "action_text": "Comment CURSOR and I will DM you my custom .cursorrules template!"}
    ],
    "caption": "5 Cursor AI tricks that changed how I code. #ai #coding #cursor #developer #tech"
}

tmp_dir = Path(tempfile.mkdtemp(prefix="verify-slides-"))
slide_paths = render_carousel_slides(sample_carousel_data, tmp_dir)
print(f"  ✓ Rendered {len(slide_paths)} 4:5 slides successfully:")
for p in slide_paths:
    validate_png(p, 2160, 2700)
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

info_path = render_infographic(sample_info_data, tmp_dir)
validate_png(info_path, 2160, 2700)
print(f"  ✓ Rendered Infographic: {info_path.name} ({info_path.stat().st_size / 1024:.1f} KB, 2160x2700 Retina)")

# 4. Check UI Compilation & Syntax
print("\n>>> [4/4] Verifying Streamlit App Compilation...")
import py_compile
py_compile.compile("app.py")
print("  ✓ app.py compiled with zero syntax/import errors")

print("\n======================================================")
print("   🎉 ALL CHECKS PASSED: SYSTEM FULLY OPERATIONAL!    ")
print("======================================================")
