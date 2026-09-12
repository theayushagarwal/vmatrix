"""
cli.py
------
Interactive Local Terminal Interface for Vmatrix Social OS:
Run the entire AI Social Engine 100% locally from your terminal without Streamlit!
- Discover & filter trending topics with 5-stage funnel
- Plan & render 4K Retina Pure-White carousels
- Scrape competitor handles & detect 3-gate viral outliers
- Reverse-engineer hook psychology & slide pacing with Groq
- Adapt competitor blueprints into original Vmatrix carousels
- Run full autonomous publishing cycle
"""

import os
import sys
import argparse
import tempfile
from pathlib import Path
from dotenv import load_dotenv

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
    generate_cheatsheet_content,
    render_carousel_slides,
    render_carousel_flow_slides,
    render_cheatsheet_slide,
    InstaScraper,
    analyze_post_virality,
    detect_viral_outliers,
    record_post,
    db,
)


CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_banner():
    print(f"{CYAN}{BOLD}")
    print("=" * 68)
    print("   ⚡ VMATRIX.CO SOCIAL OS · LOCAL TERMINAL MISSION CONTROL ⚡")
    print("   100% Autonomous Social Engine · Zero Browser Required")
    print("=" * 68)
    print(f"{RESET}")


def menu_run_funnel():
    print(f"\n{YELLOW}[1] Running 5-Stage Live Trend Funnel...{RESET}")
    geo = input(f"{BOLD}Select Trends Region (IN/US) [default: IN]: {RESET}").strip().upper() or "IN"
    print(f"📡 Harvesting live signals from 4 data feeds (Region: {geo})...")
    raw_feeds = fetch_all_feeds(geo=geo, max_per_feed=10)
    all_items = []
    for f, items in raw_feeds.items():
        all_items.extend(items)
    print(f"Harvested {len(all_items)} raw signals. Running 5-Stage Funnel...")
    results = run_filtering_funnel(all_items)
    sc = results.get("stage_counts", {})
    print(f"\n{GREEN}--- Funnel Drop-off Results ---{RESET}")
    print(f"• Raw Inputs: {sc.get('raw', 0)}")
    print(f"• Stage 1 (Blacklist): {sc.get('stage1_blacklist', 0)}")
    print(f"• Stage 2 (Positive Niche): {sc.get('stage2_niche', 0)}")
    print(f"• Stage 3 (Groq 120B Semantic): {sc.get('stage3_semantic', 0)}")
    print(f"• Stage 4 (Vector Anti-Dup): {sc.get('stage4_dedup', 0)}")
    print(f"• Stage 5 (Actionability Winners): {sc.get('stage5_actionable', 0)}")

    winners = results.get("winning_topics", [])
    if winners:
        print(f"\n{MAGENTA}{BOLD}🏆 Top Vetted Winning Topics:{RESET}")
        for i, w in enumerate(winners[:5]):
            print(f"  [{i+1}] {w.get('refined_title') or w.get('title')} ({w.get('semantic_category')}) - Score: {w.get('actionability_score')}/10")
            print(f"      Hook: \"{w.get('hook_angle', '')}\"")


def menu_generate_carousel():
    print(f"\n{YELLOW}[2] Generate & Render 4K Carousel...{RESET}")
    topic = input(f"{BOLD}Enter Topic [or press Enter for sample '5 Docker Production Tricks']: {RESET}").strip()
    if not topic:
        topic = "5 Production Docker Tricks to Shrink Container Size by 80%"

    print(f"\nFormat: [1] Listicle Tool Cards (Default)  |  [2] Architecture Flowchart")
    fmt_choice = input("Choice [1/2]: ").strip()
    mode = "flow" if fmt_choice == "2" else "listicle"

    print(f"\n🧠 Planning structured {mode} content with Groq (openai/gpt-oss-120b)...")
    if mode == "flow":
        content = generate_flow_carousel_content(topic)
    else:
        content = generate_carousel_content(topic)

    title = content.get("series_title") or content.get("cover_title") or topic
    print(f"{GREEN}✓ Structured content planned: \"{title}\"{RESET}")

    out_dir = Path("./output_slides")
    out_dir.mkdir(exist_ok=True)
    print(f"🎨 Rendering 4K Pure White Retina slides with Playwright to {out_dir.resolve()}...")
    if mode == "flow":
        paths = render_carousel_flow_slides(content, out_dir, image_format="jpeg")
    else:
        paths = render_carousel_slides(content, out_dir, image_format="jpeg")

    print(f"{GREEN}{BOLD}🎉 Successfully rendered {len(paths)} 4K slides!{RESET}")
    for p in paths:
        print(f"   🖼️ {p}")

    record_post(title=title, category=content.get("category", "AI & CODING"), hook=content.get("hook_line", ""))
    print(f"💾 Recorded to 30-day post history memory.")


def menu_competitor_spy():
    print(f"\n{YELLOW}[3] Competitor Instagram Scraping & 3-Gate Outlier Detection...{RESET}")
    handle = input(f"{BOLD}Enter Competitor Instagram Handle [default: codewithharry]: {RESET}").strip() or "codewithharry"
    handle = handle.replace("@", "").strip()
    niche = "AI & CODING"

    scraper = InstaScraper()
    print(f"🚀 Scraping @{handle} via Apify / Cache...")
    posts = scraper.scrape(handle=handle, niche=niche, limit=6, force=False)
    print(f"Ingested {len(posts)} posts for @{handle}.")

    print("\n📐 Running 3-Gate Mathematical Outlier Detection & Time Decay Scoring...")
    outlier_pipeline = detect_viral_outliers(posts, multiplier_threshold=1.5, min_cohort_size=2)
    outliers = outlier_pipeline.get("outliers", [])
    all_eval = outlier_pipeline.get("all_evaluated", [])

    print(f"Evaluated {len(all_eval)} posts across cohorts.")
    print(f"{GREEN}{BOLD}Flagged {len(outliers)} confirmed Viral Outliers meeting all 3 gates!{RESET}")

    for idx, p in enumerate(all_eval):
        is_out = p.get("is_outlier")
        badge = p.get("badge_text", "Standard")
        likes = p.get("likes", 0)
        views = p.get("views", 0)
        sc = p.get("shortcode", f"post_{idx}")
        print(f"\n[{idx+1}] @{p.get('handle')} ({sc}) - {badge}")
        print(f"    Likes: {likes:,} | Views: {views:,}")
        if is_out:
            print(f"    {GREEN}🔥 Gate 1: {p.get('gate_1', {}).get('description')}{RESET}")
            print(f"    {GREEN}🔥 Gate 2: {p.get('gate_2', {}).get('description')}{RESET}")
            print(f"    {GREEN}🔥 Gate 3: {p.get('gate_3', {}).get('description')}{RESET}")
            print(f"    {GREEN}📉 Time Decay Score: {p.get('virality_score')}x{RESET}")

    if all_eval:
        anlz_choice = input(f"\n{BOLD}Would you like to reverse-engineer post #1 with Groq AI? (y/n) [y]: {RESET}").strip().lower()
        if anlz_choice in ("", "y", "yes"):
            target_post = outliers[0] if outliers else all_eval[0]
            print(f"🧠 Reverse-engineering post '{target_post.get('shortcode')}'...")
            analysis = analyze_post_virality(target_post)
            print(f"\n{MAGENTA}--- AI Reverse-Engineering Dossier ---{RESET}")
            print(f"• Virality Score: {analysis.get('virality_score')}/100")
            print(f"• Hook Type: {analysis.get('hook_analysis', {}).get('hook_type')}")
            print(f"• Hook Trigger: {analysis.get('hook_analysis', {}).get('psychological_trigger')}")
            print(f"• Slide Pacing: {analysis.get('slide_pacing', {}).get('pacing_analysis')}")
            print(f"• Why It Went Viral: {analysis.get('why_it_went_viral')}")
            bp = analysis.get("vmatrix_blueprint", {})
            print(f"\n{GREEN}{BOLD}🚀 Vmatrix Adaptation Blueprint:{RESET}")
            print(f"• Adapted Title: \"{bp.get('adapted_title')}\"")
            print(f"• Hook Line: \"{bp.get('hook_line')}\"")
            print(f"• Competitive Advantage: {bp.get('competitive_advantage')}")

            adapt_render = input(f"\n{BOLD}Render this adapted blueprint into 4K slides right now? (y/n) [y]: {RESET}").strip().lower()
            if adapt_render in ("", "y", "yes"):
                topic = bp.get("adapted_title") or f"Mastering {target_post.get('caption')[:30]}"
                content = generate_carousel_content(topic)
                out_dir = Path("./output_slides")
                out_dir.mkdir(exist_ok=True)
                paths = render_carousel_slides(content, out_dir, image_format="jpeg")
                print(f"{GREEN}🎉 Rendered {len(paths)} slides for adapted topic '{topic}'! Saved to {out_dir.resolve()}{RESET}")


def menu_run_autonomous():
    print(f"\n{YELLOW}[4] Running Autonomous 24/7 Publishing Runner...{RESET}")
    from autonomous_publisher import run_autonomous_cycle
    run_autonomous_cycle()


def main():
    parser = argparse.ArgumentParser(description="Vmatrix Social OS CLI")
    parser.add_argument("--funnel", action="store_true", help="Run 5-stage live trend funnel")
    parser.add_argument("--generate", type=str, help="Generate and render carousel for topic")
    parser.add_argument("--format", type=str, default="listicle", choices=["listicle", "flow"], help="Carousel format")
    parser.add_argument("--scrape", type=str, help="Scrape competitor handle and detect outliers")
    parser.add_argument("--autonomous", action="store_true", help="Run full autonomous publishing cycle")

    args = parser.parse_args()

    if args.funnel:
        menu_run_funnel()
        return
    if args.generate:
        content = generate_flow_carousel_content(args.generate) if args.format == "flow" else generate_carousel_content(args.generate)
        out_dir = Path("./output_slides")
        out_dir.mkdir(exist_ok=True)
        paths = render_carousel_flow_slides(content, out_dir) if args.format == "flow" else render_carousel_slides(content, out_dir)
        print(f"Rendered {len(paths)} slides to {out_dir.resolve()}")
        return
    if args.scrape:
        scraper = InstaScraper()
        posts = scraper.scrape(args.scrape, "AI & CODING")
        outliers = detect_viral_outliers(posts)
        print(f"Found {outliers['outlier_count']} outliers across {outliers['total_evaluated']} posts.")
        return
    if args.autonomous:
        menu_run_autonomous()
        return

    # Interactive Loop
    while True:
        print_banner()
        print(f"{BOLD}What would you like to run locally?{RESET}")
        print("  1. 🎯 Run 5-Stage Live Trend Discovery & Funnel")
        print("  2. 🎨 Plan & Render 4K Carousel from Topic")
        print("  3. 🕵️ Scrape Competitor Instagram & Detect 3-Gate Outliers")
        print("  4. 🤖 Run Full Autonomous Publishing Pipeline (Zero UI)")
        print("  5. 🚪 Exit")
        choice = input(f"\n{BOLD}Select an option [1-5]: {RESET}").strip()

        if choice == "1":
            menu_run_funnel()
        elif choice == "2":
            menu_generate_carousel()
        elif choice == "3":
            menu_competitor_spy()
        elif choice == "4":
            menu_run_autonomous()
        elif choice in ("5", "q", "exit"):
            print("Goodbye!")
            break
        else:
            print(f"{RED}Invalid selection. Please choose 1-5.{RESET}")

        input(f"\n{CYAN}Press Enter to return to menu...{RESET}")


if __name__ == "__main__":
    main()
