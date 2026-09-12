"""
app.py
-------
Streamlit demo UI for ai-social-engine:
1. Discover breaking trends across 4 core data feeds (Google Trends, TechCrunch AI, VentureBeat AI, Hacker News).
2. Process raw trends through the 5-Stage Filtering Funnel (Blacklist -> Niche Scoring -> Semantic LLM -> Vector Anti-Dup -> Actionability Score).
3. Gemini 2.5 Flash plans a high-converting structured carousel.
4. Playwright renders it into on-brand 4:5 Retina slides.
5. Cloudinary + Meta Graph API publishes it straight to Instagram.
"""

import os
import tempfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from core import (
    generate_carousel_content,
    generate_cheatsheet_content,
    generate_flow_carousel_content,
    render_carousel_slides,
    render_carousel_flow_slides,
    render_infographic,
    upload_images_to_cloudinary,
    publish_to_instagram_carousel,
    publish_to_instagram_photo,
    generate_post_comment,
    fetch_all_feeds,
    fetch_google_trends,
    fetch_techcrunch_ai,
    fetch_venturebeat_ai,
    fetch_hacker_news,
    run_filtering_funnel,
    record_post,
    get_recent_posts,
    queue_post_for_approval,
    load_approval_queue,
    get_pending_approvals,
    get_approval_history,
    get_time_remaining,
    extend_approval_timeout,
    update_queued_post,
    approve_and_publish_post,
    reject_queued_post,
    process_auto_publish_timeouts,
    fetch_posts_from_supabase,
    fetch_top_performing_posts_from_supabase,
    audit_published_posts_insights,
    get_top_performing_topics,
    InstaScraper,
    analyze_post_virality,
    detect_viral_outliers,
    process_post_outlier_status,
    db,
)

load_dotenv()

# ---------------------------------------------------------------------------
# Page config + custom styling
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Vmatrix Social OS · Autonomous Engine",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

    /* Global Typography & Base */
    html, body, [class*="css"], .stApp {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
        background-color: #080b14 !important;
        background-image: 
            radial-gradient(ellipse 90% 60% at 50% -20%, rgba(99, 102, 241, 0.22), transparent 70%),
            radial-gradient(circle at 95% 75%, rgba(236, 72, 153, 0.08), transparent 50%),
            radial-gradient(circle at 5% 35%, rgba(56, 189, 248, 0.07), transparent 40%) !important;
        background-attachment: fixed !important;
        color: #f1f5f9 !important;
        letter-spacing: -0.01em;
    }

    code, pre, .mono-font {
        font-family: 'JetBrains Mono', monospace !important;
    }

    .block-container {
        padding-top: 1.8rem !important;
        padding-bottom: 3.5rem !important;
        max-width: 1280px !important;
    }

    h1, h2, h3, h4, h5, h6 {
        font-weight: 800 !important;
        letter-spacing: -0.03em !important;
        color: #ffffff !important;
    }

    /* Sidebar Mission Control */
    section[data-testid="stSidebar"] {
        background-color: #0c101c !important;
        background-image: linear-gradient(180deg, rgba(15, 23, 42, 0.96) 0%, rgba(8, 11, 20, 0.98) 100%) !important;
        border-right: 1px solid rgba(255, 255, 255, 0.08) !important;
        box-shadow: 4px 0 30px rgba(0, 0, 0, 0.5) !important;
    }

    /* Hero Banner HUD */
    .hero-container {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.45) 0%, rgba(15, 23, 42, 0.75) 100%);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 20px;
        padding: 24px 28px;
        margin-bottom: 24px;
        box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.15);
        position: relative;
        overflow: hidden;
    }

    .hero-container::before {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 2px;
        background: linear-gradient(90deg, #6366f1, #a855f7, #ec4899, #38bdf8);
    }

    .hero-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 12px;
        background: rgba(99, 102, 241, 0.15);
        border: 1px solid rgba(99, 102, 241, 0.35);
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        color: #a5b4fc;
        margin-bottom: 10px;
    }

    .hero-title {
        font-size: 2.2rem;
        font-weight: 800;
        letter-spacing: -0.04em;
        line-height: 1.15;
        margin: 0 0 8px 0;
        background: linear-gradient(135deg, #ffffff 30%, #cbd5e1 70%, #94a3b8 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }

    .hero-sub {
        font-size: 0.95rem;
        color: #94a3b8;
        line-height: 1.45;
        margin: 0;
    }

    /* Live Pulsing Dot */
    @keyframes pulse-glow {
        0%, 100% { opacity: 1; transform: scale(1); filter: drop-shadow(0 0 6px #22c55e); }
        50% { opacity: 0.45; transform: scale(0.9); filter: drop-shadow(0 0 1px #22c55e); }
    }
    .pulse-dot {
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background-color: #22c55e;
        animation: pulse-glow 2s infinite ease-in-out;
        vertical-align: middle;
        margin-right: 6px;
    }

    /* Telemetry HUD Strip */
    .telemetry-strip {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        margin-top: 16px;
        padding-top: 16px;
        border-top: 1px solid rgba(255, 255, 255, 0.08);
    }
    .telemetry-item {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 0.78rem;
        font-weight: 600;
        color: #cbd5e1;
        background: rgba(15, 23, 42, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.06);
        padding: 4px 10px;
        border-radius: 8px;
    }

    /* Modern Floating Segmented Tabs Dock */
    div[data-baseweb="tab-list"] {
        background: rgba(15, 23, 42, 0.85) !important;
        backdrop-filter: blur(18px) !important;
        -webkit-backdrop-filter: blur(18px) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 16px !important;
        padding: 6px 8px !important;
        gap: 6px !important;
        margin-bottom: 24px !important;
        box-shadow: 0 8px 30px rgba(0, 0, 0, 0.4) !important;
    }
    button[data-baseweb="tab"] {
        border-radius: 10px !important;
        padding: 9px 18px !important;
        color: #94a3b8 !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        border: 1px solid transparent !important;
        background: transparent !important;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    button[data-baseweb="tab"]:hover {
        color: #ffffff !important;
        background: rgba(255, 255, 255, 0.06) !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        background: linear-gradient(135deg, rgba(99, 102, 241, 0.28) 0%, rgba(168, 85, 247, 0.28) 100%) !important;
        color: #ffffff !important;
        border: 1px solid rgba(129, 140, 248, 0.45) !important;
        box-shadow: 0 4px 18px rgba(99, 102, 241, 0.3) !important;
        font-weight: 700 !important;
    }
    div[data-baseweb="tab-highlight"] {
        display: none !important;
    }

    /* Primary Buttons */
    button[kind="primary"], .stButton > button[type="primary"] {
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 50%, #d946ef 100%) !important;
        color: #ffffff !important;
        border: 1px solid rgba(255, 255, 255, 0.25) !important;
        border-radius: 12px !important;
        font-weight: 700 !important;
        letter-spacing: -0.01em !important;
        padding: 0.60rem 1.4rem !important;
        box-shadow: 0 4px 20px rgba(124, 58, 237, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.3) !important;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    button[kind="primary"]:hover, .stButton > button[type="primary"]:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 28px rgba(124, 58, 237, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.4) !important;
        border-color: rgba(255, 255, 255, 0.45) !important;
    }

    /* Secondary Buttons */
    button[kind="secondary"], .stButton > button:not([type="primary"]) {
        background: rgba(30, 41, 59, 0.5) !important;
        backdrop-filter: blur(12px) !important;
        color: #e2e8f0 !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        border-radius: 12px !important;
        font-weight: 600 !important;
        transition: all 0.2s ease !important;
    }
    button[kind="secondary"]:hover, .stButton > button:not([type="primary"]):hover {
        background: rgba(51, 65, 85, 0.65) !important;
        border-color: rgba(129, 140, 248, 0.4) !important;
        color: #ffffff !important;
        transform: translateY(-1px) !important;
    }

    /* Inputs & Select Boxes */
    .stTextInput > div > div > input,
    .stSelectbox > div > div > div,
    .stTextArea > div > div > textarea {
        background: rgba(15, 23, 42, 0.7) !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        border-radius: 12px !important;
        color: #f8fafc !important;
        font-size: 0.92rem !important;
        padding: 10px 14px !important;
        transition: all 0.2s ease !important;
    }
    .stTextInput > div > div > input:focus,
    .stSelectbox > div > div > div:focus,
    .stTextArea > div > div > textarea:focus {
        border-color: #818cf8 !important;
        box-shadow: 0 0 0 3px rgba(129, 140, 248, 0.25) !important;
    }

    /* Glass Cards & Expanders */
    div[data-testid="stExpander"] {
        background: rgba(15, 23, 42, 0.6) !important;
        backdrop-filter: blur(16px) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 16px !important;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3) !important;
        overflow: hidden;
        margin-bottom: 20px;
    }

    .feed-card {
        background: rgba(15, 23, 42, 0.65);
        backdrop-filter: blur(14px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 18px 20px;
        margin-bottom: 14px;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .feed-card:hover {
        transform: translateY(-2px);
        border-color: rgba(129, 140, 248, 0.45);
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4), 0 0 15px rgba(99, 102, 241, 0.1);
    }

    .funnel-card {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.65) 0%, rgba(15, 23, 42, 0.85) 100%);
        backdrop-filter: blur(16px);
        border: 1px solid rgba(129, 140, 248, 0.35);
        border-radius: 18px;
        padding: 22px 24px;
        margin-bottom: 16px;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .funnel-card:hover {
        transform: translateY(-2px);
        border-color: rgba(129, 140, 248, 0.6);
        box-shadow: 0 12px 30px rgba(0, 0, 0, 0.4);
    }

    .stat-pill {
        background: rgba(15, 23, 42, 0.65);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
        padding: 12px 14px;
        text-align: center;
        transition: all 0.2s ease;
    }
    .stat-pill:hover {
        border-color: rgba(129, 140, 248, 0.35);
        transform: translateY(-1px);
    }
    .stat-val { font-size: 1.35rem; font-weight: 800; color: #818cf8; }
    .stat-lbl { font-size: 0.72rem; color: #94a3b8; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; margin-top: 2px; }

    /* Outlier Glow Cards */
    .outlier-glow-card {
        background: linear-gradient(135deg, rgba(30, 27, 75, 0.4) 0%, rgba(15, 23, 42, 0.85) 100%);
        backdrop-filter: blur(16px);
        border: 1px solid rgba(244, 63, 94, 0.45);
        border-radius: 18px;
        padding: 20px 24px;
        margin-bottom: 16px;
        box-shadow: 0 0 25px rgba(244, 63, 94, 0.12), 0 8px 24px rgba(0, 0, 0, 0.4);
        transition: all 0.2s ease;
    }
    .outlier-glow-card:hover {
        border-color: rgba(244, 63, 94, 0.7);
        box-shadow: 0 0 35px rgba(244, 63, 94, 0.22), 0 12px 30px rgba(0, 0, 0, 0.5);
    }

    div[data-testid="stImage"] img {
        border-radius: 14px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        box-shadow: 0 8px 20px rgba(0, 0, 0, 0.3);
    }

    .queue-card {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.92) 100%);
        border: 1px solid rgba(129, 140, 248, 0.35);
        border-radius: 20px;
        padding: 24px;
        margin-bottom: 24px;
        box-shadow: 0 12px 30px rgba(0, 0, 0, 0.4);
    }
    .timer-badge {
        display: inline-flex; align-items: center; gap: 8px;
        padding: 6px 16px; border-radius: 999px; font-weight: 700; font-size: 0.90rem;
    }
    .timer-urgent { background: rgba(239, 68, 68, 0.18); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.45); }
    .timer-warning { background: rgba(245, 158, 11, 0.18); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.45); }
    .timer-normal { background: rgba(52, 211, 153, 0.18); color: #34d399; border: 1px solid rgba(52, 211, 153, 0.45); }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session state initialization
# ---------------------------------------------------------------------------
if "content" not in st.session_state:
    st.session_state.content = None
if "slide_paths" not in st.session_state:
    st.session_state.slide_paths = None
if "topic" not in st.session_state:
    st.session_state.topic = ""
if "feed_geo" not in st.session_state:
    st.session_state.feed_geo = "IN"
if "funnel_results" not in st.session_state:
    st.session_state.funnel_results = None
if "carousel_mode" not in st.session_state:
    st.session_state.carousel_mode = "listicle"

# ---------------------------------------------------------------------------
# Section 1: 🎯 5-Stage Filtering Funnel (Curator Auto-Pilot)
# ---------------------------------------------------------------------------
with st.expander("🎯 **5-Stage Filtering Funnel (Auto-Pilot Curator)** — Turn 100+ raw trends into vetted winners", expanded=True):
    col_funnel_btn, col_funnel_info = st.columns([1, 3])
    with col_funnel_btn:
        if st.button("🚀 Run 5-Stage Funnel", type="primary", use_container_width=True):
            with st.spinner("Harvesting live feeds & filtering through 5 stages…"):
                all_raw = load_cached_feeds(st.session_state.feed_geo)
                combined_items = []
                for feed_name, items in all_raw.items():
                    combined_items.extend(items)
                
                results = run_filtering_funnel(combined_items)
                st.session_state.funnel_results = results

    with col_funnel_info:
        st.caption("Filters raw signals through: **Blacklist** → **Positive Niche Scoring** → **Semantic LLM** → **Vector Anti-Dup (Cosine)** → **Actionability Fit**")

    if st.session_state.get("funnel_results"):
        f_res = st.session_state.funnel_results
        sc = f_res.get("stage_counts", {})
        
        # Display 5-Stage Funnel Metrics Bar
        st.markdown("##### 📊 Funnel Drop-off Pipeline")
        m_cols = st.columns(6)
        with m_cols[0]:
            st.markdown(f'<div class="stat-pill"><div class="stat-val">{sc.get("raw", 0)}</div><div class="stat-lbl">Raw In</div></div>', unsafe_allow_html=True)
        with m_cols[1]:
            st.markdown(f'<div class="stat-pill"><div class="stat-val">{sc.get("stage1_blacklist", 0)}</div><div class="stat-lbl">Stage 1: Clean</div></div>', unsafe_allow_html=True)
        with m_cols[2]:
            st.markdown(f'<div class="stat-pill"><div class="stat-val">{sc.get("stage2_niche", 0)}</div><div class="stat-lbl">Stage 2: Niche</div></div>', unsafe_allow_html=True)
        with m_cols[3]:
            st.markdown(f'<div class="stat-pill"><div class="stat-val">{sc.get("stage3_semantic", 0)}</div><div class="stat-lbl">Stage 3: LLM</div></div>', unsafe_allow_html=True)
        with m_cols[4]:
            st.markdown(f'<div class="stat-pill"><div class="stat-val">{sc.get("stage4_dedup", 0)}</div><div class="stat-lbl">Stage 4: Dedup</div></div>', unsafe_allow_html=True)
        with m_cols[5]:
            st.markdown(f'<div class="stat-pill" style="border-color: #34d399;"><div class="stat-val" style="color: #34d399;">{sc.get("stage5_actionable", 0)}</div><div class="stat-lbl">🏆 Winners</div></div>', unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("##### 🏆 Top Vetted Winning Topics")
        
        winners = f_res.get("winning_topics", [])
        if not winners:
            st.info("No candidates made it past all 5 stages in this batch. Try refreshing feeds.")
        else:
            w_cols = st.columns(min(len(winners), 3))
            for i, winner in enumerate(winners[:3]):
                with w_cols[i]:
                    cat = winner.get("semantic_category") or winner.get("category", "AI & CODING")
                    badge_cls = "badge-ai" if "AI" in cat else ("badge-fin" if "FIN" in cat else "badge-tools")
                    score = winner.get("actionability_score", 8)
                    steps = winner.get("step_ideas", [])
                    steps_html = "".join([f"<li>{s}</li>" for s in steps[:3]])

                    st.markdown(
                        f"""
                        <div class="funnel-card">
                            <span class="funnel-step-badge {badge_cls}">{cat}</span>
                            <span style="float: right; color: #4ade80; font-weight: 700; font-size: 0.85rem;">🎯 Score {score}/10</span>
                            <div class="feed-title" style="margin-top: 6px;">{winner.get('refined_title') or winner.get('title')}</div>
                            <div class="feed-summary" style="font-style: italic; color: #cbd5e1;">&ldquo;{winner.get('hook_angle', winner.get('summary', ''))}&rdquo;</div>
                            <div style="font-size: 0.80rem; color: #94a3b8; margin-bottom: 12px;">
                                <strong>Slide Structure:</strong>
                                <ul style="padding-left: 18px; margin-top: 4px;">{steps_html}</ul>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    if st.button("⚡ Generate From This Winner", key=f"win_btn_{i}", type="primary", use_container_width=True):
                        st.session_state.topic = winner.get("refined_title") or winner.get("title")
                        st.rerun()

# ---------------------------------------------------------------------------
# Section 2: 📡 Real-Time Topic Radar (4 Core Data Feeds)
# ---------------------------------------------------------------------------
with st.expander("📡 **Raw Topic Radar (4 Live Feeds)** — Browse individual raw feed signals", expanded=False):
    col_radar_hdr, col_geo, col_refresh = st.columns([3, 1, 1])
    with col_radar_hdr:
        st.caption("Live trending signals gathered from Google Trends, TechCrunch AI, VentureBeat AI, and Hacker News:")
    with col_geo:
        selected_geo = st.selectbox("Trends Region", options=["IN", "US"], format_func=lambda x: "🇮🇳 India" if x == "IN" else "🌐 Global / US", index=0 if st.session_state.feed_geo == "IN" else 1, label_visibility="collapsed")
        st.session_state.feed_geo = selected_geo
    with col_refresh:
        if st.button("🔄 Refresh Feeds", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    with st.spinner("Fetching live signals across 4 data feeds…"):
        feeds = load_cached_feeds(st.session_state.feed_geo)

    feed_tabs = st.tabs([
        f"📈 Google Trends ({'India' if st.session_state.feed_geo == 'IN' else 'Global'})",
        "🤖 TechCrunch AI",
        "🏢 VentureBeat AI",
        "💻 Hacker News",
    ])

    def render_feed_items(items: list, feed_id: str):
        if not items:
            st.info("No active signals found for this feed right now.")
            return

        col1, col2 = st.columns(2)
        for idx, item in enumerate(items[:8]):
            target_col = col1 if idx % 2 == 0 else col2
            with target_col:
                st.markdown(
                    f"""
                    <div class="feed-card">
                        <div class="feed-title">{item['title']}</div>
                        <div class="feed-summary">{item['summary']}</div>
                        <div class="feed-meta">
                            <span>{item['metric']}</span>
                            <span>•</span>
                            <a href="{item['url']}" target="_blank" style="color: #38bdf8; text-decoration: none;">Read source ↗</a>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button(f"⚡ Use This Topic", key=f"btn_{feed_id}_{idx}", use_container_width=True):
                    st.session_state.topic = item["title"]
                    st.rerun()

    with feed_tabs[0]:
        render_feed_items(feeds.get("google_trends", []), "gt")
    with feed_tabs[1]:
        render_feed_items(feeds.get("techcrunch_ai", []), "tc")
    with feed_tabs[2]:
        render_feed_items(feeds.get("venturebeat_ai", []), "vb")
    with feed_tabs[3]:
        render_feed_items(feeds.get("hacker_news", []), "hn")

st.markdown("---")

# ---------------------------------------------------------------------------
# Topic Input + Presets Launchpad
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
        <span style="font-weight: 700; font-size: 1.05rem; color: #f8fafc;">🎯 Carousel Concept Launchpad</span>
        <span style="font-size: 0.80rem; color: #818cf8; font-weight: 600;">Groq 120B Structured Planner</span>
    </div>
    """,
    unsafe_allow_html=True,
)

topic_input = st.text_input(
    "Topic",
    value=st.session_state.topic,
    placeholder="Enter an engineering topic (e.g. 5 Production Docker Tricks, FastAPI Concurrency, LangGraph Architecture)...",
    label_visibility="collapsed",
)

st.session_state.topic = topic_input or st.session_state.topic

st.markdown(
    """
    <div style="display: flex; align-items: center; gap: 8px; margin-top: 10px; margin-bottom: 6px;">
        <span style="font-size: 0.80rem; color: #94a3b8; font-weight: 600;">⚡ Quick Presets:</span>
    </div>
    """,
    unsafe_allow_html=True,
)
preset_cols = st.columns(3)
for i, preset in enumerate(PRESETS):
    with preset_cols[i]:
        if st.button(preset, use_container_width=True, key=f"top_pre_{i}"):
            topic_input = preset.split(" ", 1)[1]
            st.session_state.topic = topic_input
            st.rerun()

st.session_state.topic = topic_input or st.session_state.topic

ctrl_c1, ctrl_c2, ctrl_c3 = st.columns([2.5, 1.2, 1.3])
with ctrl_c1:
    selected_mode = st.radio(
        "Carousel Canvas Architecture",
        options=["listicle", "flow"],
        format_func=lambda x: "📋 Listicle / Tool Cards (5 Slides)" if x == "listicle" else "🗺️ System Flowchart (5 Slides)",
        horizontal=True,
        index=0 if st.session_state.carousel_mode == "listicle" else 1,
    )
    st.session_state.carousel_mode = selected_mode

with ctrl_c2:
    export_fmt = st.selectbox(
        "Output Render Quality",
        options=["jpeg", "png"],
        format_func=lambda x: "⚡ JPEG 4K Retina" if x == "jpeg" else "🖼️ PNG Lossless",
        index=0,
    )

with ctrl_c3:
    st.write("") # spacing
    generate_clicked = st.button("✨ Plan & Render", type="primary", use_container_width=True)

st.markdown("---")

tab_queue, tab_content, tab_preview, tab_publish, tab_analytics, tab_competitors = st.tabs(
    [
        "⏱️ 30-Min Approval Queue",
        "📋 Content Generation",
        "🖼️ Visual Carousel Preview",
        "🚀 Live Publishing",
        "📈 Analytics & Supabase Feedback",
        "🕵️ Competitor Spy & Virality AI",
    ]
)

# ---------------------------------------------------------------------------
# Generation flow
# ---------------------------------------------------------------------------
if "last_failed_stage" not in st.session_state:
    st.session_state.last_failed_stage = None
if "pending_content" not in st.session_state:
    st.session_state.pending_content = None

def run_pipeline(topic: str, skip_generate: bool = False, img_format: str = "jpeg"):
    """
    Runs generate -> render as one pipeline with stage tracking.
    Supports both Listicle Tool Cards and Architecture Flowchart carousels.
    """
    mode = st.session_state.carousel_mode
    progress = st.progress(0, text="Initializing Groq (openai/gpt-oss-120b)…")
    content = st.session_state.pending_content if skip_generate else None

    if content is None:
        try:
            if mode == "flow":
                progress.progress(20, text="Planning System Architecture Flowchart with Groq…")
                content = generate_flow_carousel_content(topic)
            else:
                progress.progress(20, text="Planning structured carousel with Groq…")
                content = generate_carousel_content(topic)
            st.session_state.pending_content = content
        except Exception as e:
            st.session_state.last_failed_stage = "generate"
            progress.empty()
            st.error(
                f"**Content generation failed**: {e}\n\n"
                "This step retries transient failures automatically with multi-model failover — "
                "if it still failed, check your `GROQ_API_KEY` in `.env`."
            )
            return

    try:
        progress.progress(55, text="Rendering 4K Retina slides with batch Playwright…")
        tmp_dir = Path(tempfile.mkdtemp(prefix="ai-social-"))
        if mode == "flow":
            slide_paths = render_carousel_flow_slides(content, tmp_dir, image_format=img_format)
        else:
            slide_paths = render_carousel_slides(content, tmp_dir, image_format=img_format)

        progress.progress(100, text="Done.")
        st.session_state.content = content
        st.session_state.slide_paths = slide_paths
        st.session_state.last_failed_stage = None
        st.session_state.pending_content = None

        # Automatically record to 30-day post history memory for deduplication
        record_post(
            title=content.get("series_title") or content.get("cover_title") or topic,
            category=content.get("category", "AI & CODING"),
            hook=content.get("hook_line") or content.get("cover_subtitle", ""),
        )

        display_title = content.get("series_title") or content.get("cover_title", "your carousel")
        st.success(f"Generated \"{display_title}\" — 5 slides ready & recorded to memory.")
    except Exception as e:
        st.session_state.last_failed_stage = "render"
        progress.empty()
        st.error(
            f"**Slide rendering failed** (Playwright): {e}\n\n"
            "Each slide render is retried automatically and checked for a "
            "blank/broken frame before being accepted. The content plan itself was "
            "generated successfully and won't be regenerated on retry."
        )


if generate_clicked:
    if not st.session_state.topic.strip():
        st.warning("Enter a topic first or pick one from the Funnel/Radar above.")
    else:
        st.session_state.pending_content = None
        run_pipeline(st.session_state.topic, img_format=export_fmt)

if st.session_state.last_failed_stage == "generate":
    if st.button("🔁 Retry content generation", use_container_width=True):
        run_pipeline(st.session_state.topic, img_format=export_fmt)
elif st.session_state.last_failed_stage == "render":
    if st.button("🔁 Retry rendering (reuses existing content plan)", use_container_width=True):
        run_pipeline(st.session_state.topic, skip_generate=True, img_format=export_fmt)

# ---------------------------------------------------------------------------
# Tab 0: 30-Min Human Approval Queue
# ---------------------------------------------------------------------------
with tab_queue:
    # Heartbeat check for auto-publish timeouts
    auto_pub_setting = st.session_state.get("auto_publish_enabled", True)
    try:
        expired_published = process_auto_publish_timeouts(auto_publish_enabled=auto_pub_setting)
        if expired_published:
            st.info(f"⚡ Auto-pilot processed {len(expired_published)} post(s) whose 30-minute grace period expired.")
    except Exception as e:
        logger.warning("Auto-publish timeout processing note: %s", e)

    pending_items = get_pending_approvals()

    # Queue Metrics Bar
    q_col1, q_col2, q_col3, q_col4 = st.columns([1.2, 1.2, 1.2, 1])
    with q_col1:
        st.markdown(
            f'<div class="stat-pill"><div class="stat-val">{len(pending_items)}</div><div class="stat-lbl">Pending Review</div></div>',
            unsafe_allow_html=True,
        )
    with q_col2:
        if pending_items:
            m, s, _ = get_time_remaining(pending_items[0])
            st.markdown(
                f'<div class="stat-pill" style="border-color: #fbbf24;"><div class="stat-val" style="color: #fbbf24;">{m}m {s}s</div><div class="stat-lbl">Next Auto-Publish</div></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="stat-pill"><div class="stat-val" style="color: #4ade80;">Ready</div><div class="stat-lbl">Queue Status</div></div>',
                unsafe_allow_html=True,
            )
    with q_col3:
        status_text = "AUTO-PILOT ON" if auto_pub_setting else "MANUAL ONLY"
        color = "#34d399" if auto_pub_setting else "#818cf8"
        st.markdown(
            f'<div class="stat-pill"><div class="stat-val" style="color: {color}; font-size: 1.05rem; padding-top: 4px;">{status_text}</div><div class="stat-lbl">30m Grace Mode</div></div>',
            unsafe_allow_html=True,
        )
    with q_col4:
        if st.button("🔄 Refresh Queue", use_container_width=True):
            st.rerun()

    st.markdown("---")

    # If pending items exist, render each one with full inspection and controls
    if pending_items:
        st.markdown(f"### ⏳ Active Posts in 30-Minute Grace Period ({len(pending_items)})")
        for item in pending_items:
            item_id = item["id"]
            mins, secs, fraction = get_time_remaining(item)

            if mins <= 5:
                timer_class = "timer-urgent"
                timer_icon = "🚨"
                status_note = "Urgent: Auto-publishing shortly unless paused or rejected!"
            elif mins <= 15:
                timer_class = "timer-warning"
                timer_icon = "⚠️"
                status_note = "Grace period halfway through. Review copy and slides below."
            else:
                timer_class = "timer-normal"
                timer_icon = "⏳"
                status_note = "Human review window active (30 minutes total)."

            st.markdown(
                f"""
                <div class="queue-card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <div>
                            <span class="funnel-step-badge badge-ai">{item.get('format', 'listicle').upper()}</span>
                            <span class="funnel-step-badge badge-tools">{item.get('slot', 'morning').upper()} SLOT</span>
                            <span class="funnel-step-badge badge-fin">VISION: {item.get('vision_score', 10.0)}/10 PASSED</span>
                        </div>
                        <div class="timer-badge {timer_class}">
                            {timer_icon} {mins:02d}m {secs:02d}s Remaining
                        </div>
                    </div>
                    <h3 style="margin-top: 0; margin-bottom: 4px;">{item.get('topic')}</h3>
                    <p style="color: #94a3b8; font-size: 0.85rem; margin-bottom: 12px;">
                        Queued at: {item.get('created_at_iso')} | {status_note}
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Visual progress countdown bar
            st.progress(fraction, text=f"Auto-publish countdown: {mins} minutes, {secs} seconds remaining")

            # Visual Slide Inspection
            slides = item.get("image_urls") or item.get("slide_paths") or []
            if slides:
                st.markdown("**🖼️ Rendered 2160×2700 Retina Slides:**")
                slide_cols = st.columns(min(5, len(slides)))
                for s_idx, sp in enumerate(slides):
                    with slide_cols[s_idx % len(slide_cols)]:
                        st.image(sp, caption=f"Slide {s_idx + 1}", use_container_width=True)

            # Editable Copy Fields
            copy_col1, copy_col2 = st.columns([1.5, 1])
            with copy_col1:
                st.markdown("**📝 Caption (Audited):**")
                edited_caption = st.text_area(
                    f"caption_{item_id}",
                    value=item.get("caption", ""),
                    height=140,
                    label_visibility="collapsed",
                )
            with copy_col2:
                st.markdown("**💬 Auto-Comment (Pinned First Comment):**")
                edited_comment = st.text_area(
                    f"comment_{item_id}",
                    value=item.get("auto_comment", ""),
                    height=140,
                    label_visibility="collapsed",
                )

            # Action Buttons
            btn_c1, btn_c2, btn_c3, btn_c4 = st.columns([1.5, 1, 1, 1])
            with btn_c1:
                if st.button("🚀 Approve & Publish Now", key=f"appr_{item_id}", type="primary", use_container_width=True):
                    update_queued_post(item_id, caption=edited_caption, auto_comment=edited_comment)
                    with st.spinner("Publishing post & first comment live to Instagram (@vmatrix.co)..."):
                        try:
                            res = approve_and_publish_post(item_id, auto=False)
                            st.success(f"🎉 Live on Instagram! Post ID: `{res.get('post_id')}` | Link: {res.get('permalink', 'N/A')}")
                            st.balloons()
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Publishing failed: {e}")
            with btn_c2:
                if st.button("⏱️ +15 Mins", key=f"ext_{item_id}", use_container_width=True):
                    extend_approval_timeout(item_id, extra_minutes=15)
                    st.success("Extended countdown timer by +15 minutes!")
                    time.sleep(0.5)
                    st.rerun()
            with btn_c3:
                if st.button("💾 Save Edits", key=f"save_{item_id}", use_container_width=True):
                    update_queued_post(item_id, caption=edited_caption, auto_comment=edited_comment)
                    st.success("Saved copy changes.")
                    time.sleep(0.5)
                    st.rerun()
            with btn_c4:
                if st.button("❌ Reject", key=f"rej_{item_id}", use_container_width=True):
                    reject_queued_post(item_id, reason="Rejected manually via dashboard")
                    st.warning(f"Post '{item.get('topic')}' cancelled and removed from queue.")
                    time.sleep(0.5)
                    st.rerun()

            st.markdown("---")
    else:
        st.info("✅ **No posts currently in the approval queue.** All scheduled or generated posts have been reviewed.")

    # ⚡ Test Queue Simulation Section
    with st.expander("⚡ **Send a Post to the 30-Minute Approval Queue (Stage & Review)**", expanded=False):
        st.caption("Plan, render, and enqueue a post with a 30-minute countdown timer so you can test the human approval workflow.")
        sim_topic = st.text_input("Topic to Queue", value=st.session_state.topic or "5 Claude 3.7 Prompt Engineering Hacks")
        sim_fmt = st.selectbox("Format", options=["listicle", "photo", "flow"], index=0, format_func=lambda x: "📋 Listicle (5 Slides)" if x == "listicle" else ("📸 Cheatsheet (1 Photo)" if x == "photo" else "🗺️ System Flow (5 Slides)"))
        if st.button("🚀 Plan, Render & Queue Post (30m Timer)", type="secondary"):
            with st.spinner(f"Generating and rendering '{sim_topic}' into 30-min approval queue..."):
                try:
                    import tempfile
                    from core import (
                        generate_carousel_content,
                        generate_cheatsheet_content,
                        generate_flow_carousel_content,
                        render_carousel_slides,
                        render_carousel_flow_slides,
                        render_infographic,
                        generate_post_caption,
                        generate_post_comment,
                    )
                    tmp_d = Path(tempfile.mkdtemp(prefix="queue-sim-"))
                    if sim_fmt == "photo":
                        c_plan = generate_cheatsheet_content(sim_topic)
                        ip = render_infographic(c_plan, tmp_d, image_format="jpeg")
                        s_paths = [ip]
                    elif sim_fmt == "flow":
                        c_plan = generate_flow_carousel_content(sim_topic)
                        s_paths = render_carousel_flow_slides(c_plan, tmp_d, image_format="jpeg")
                    else:
                        c_plan = generate_carousel_content(sim_topic)
                        s_paths = render_carousel_slides(c_plan, tmp_d, image_format="jpeg")

                    cap = generate_post_caption(sim_topic, c_plan, format_type=sim_fmt)
                    comm = generate_post_comment(sim_topic, c_plan, format_type=sim_fmt)

                    q_res = queue_post_for_approval(
                        topic=sim_topic,
                        format_type=sim_fmt,
                        slot="evening" if sim_fmt != "photo" else "morning",
                        slide_paths=s_paths,
                        caption=cap,
                        auto_comment=comm,
                        content_plan=c_plan,
                        timeout_minutes=30,
                        upload_cdn_now=True,
                    )
                    st.success(f"🎉 Enqueued '{sim_topic}' with 30-min approval timer (Queue ID: `{q_res['id']}`)!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to queue post: {e}")

    # 📜 Audit History Log
    with st.expander("📜 **Approval Queue History & Published Log**", expanded=False):
        history = get_approval_history(limit=15)
        if not history:
            st.caption("No past approval records yet.")
        else:
            for h in history:
                h_status = h.get("status", "unknown")
                if h_status in ("approved", "auto_published"):
                    badge_color = "#34d399"
                    status_lbl = "PUBLISHED (AUTO)" if h_status == "auto_published" else "APPROVED & PUBLISHED"
                else:
                    badge_color = "#f87171"
                    status_lbl = "REJECTED"

                st.markdown(
                    f"""
                    <div style="border-left: 3px solid {badge_color}; padding: 8px 14px; background: rgba(30,41,59,0.3); border-radius: 8px; margin-bottom: 10px;">
                        <div style="display: flex; justify-content: space-between;">
                            <strong style="color: #f3f4f8;">{h.get('topic')}</strong>
                            <span style="color: {badge_color}; font-weight: 700; font-size: 0.8rem;">{status_lbl}</span>
                        </div>
                        <div style="font-size: 0.78rem; color: #94a3b8; margin-top: 4px;">
                            Format: {h.get('format')} | Post ID: {h.get('post_id') or 'None'} | Permalink: {h.get('permalink') or 'N/A'}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

# ---------------------------------------------------------------------------
# Tab 1: structured JSON
# ---------------------------------------------------------------------------
with tab_content:
    if st.session_state.content:
        title_text = st.session_state.content.get('series_title') or st.session_state.content.get('cover_title', '')
        hook_text = st.session_state.content.get('hook_line') or st.session_state.content.get('cover_subtitle', '')
        st.markdown(f"### {title_text}")
        st.caption(hook_text)
        st.json(st.session_state.content)
    else:
        st.info("Generate a carousel to see the structured content plan here.")

# ---------------------------------------------------------------------------
# Tab 2: visual preview
# ---------------------------------------------------------------------------
with tab_preview:
    if st.session_state.slide_paths:
        cols = st.columns(5)
        for i, path in enumerate(st.session_state.slide_paths):
            with cols[i % 5]:
                st.image(str(path), caption=f"Slide {i + 1}", use_container_width=True)
    else:
        st.info("Generate a carousel to preview the rendered 4K slides here.")

# ---------------------------------------------------------------------------
# Tab 3: publishing
# ---------------------------------------------------------------------------
with tab_publish:
    if not st.session_state.slide_paths:
        st.info("Generate a carousel before publishing.")
    else:
        st.markdown("**Caption preview**")
        caption_val = st.text_area(
            "caption",
            value=st.session_state.content.get("caption", ""),
            height=130,
            label_visibility="collapsed",
        )

        st.markdown("**Auto-Comment Preview (First Comment / Discussion Starter)**")
        default_comment = st.session_state.content.get("auto_comment")
        if not default_comment:
            default_comment = generate_post_comment(
                topic=st.session_state.content.get("series_title", "Tech & AI Guide"),
                content_plan=st.session_state.content,
                format_type="listicle",
            )
            st.session_state.content["auto_comment"] = default_comment

        comment_val = st.text_area(
            "auto_comment",
            value=default_comment,
            height=70,
            label_visibility="collapsed",
        )

        col_live, col_queue = st.columns([1, 1])
        with col_live:
            if st.button("🚀 Publish to Instagram Live Now", type="primary", use_container_width=True):
                pub_progress = st.progress(0, text="Uploading slides to Cloudinary…")
                try:
                    image_urls = upload_images_to_cloudinary(st.session_state.slide_paths)
                    pub_progress.progress(35, text="Creating carousel item containers…")

                    pub_progress.progress(60, text="Waiting for Instagram to process containers…")
                    result = publish_to_instagram_carousel(
                        image_urls,
                        caption_val,
                        auto_comment=comment_val,
                    )

                    pub_progress.progress(100, text="Published.")
                    comment_badge = f" | First comment ID: `{result['comment_id']}`" if result.get("comment_id") else ""
                    st.success(f"🎉 Live on Instagram — post ID `{result['post_id']}`{comment_badge}")
                    st.balloons()
                except Exception as e:
                    pub_progress.empty()
                    st.error(
                        f"**Publishing failed:** {e}\n\n"
                        "Uploads and container creation are retried automatically with "
                        "backoff, so a failure here is either a hard auth/permissions "
                        "issue (check `IG_USER_ID` / `IG_ACCESS_TOKEN`) or Meta rejected "
                        "the request outright. Your slides are unaffected — hit the "
                        "button again once it's fixed."
                    )

        with col_queue:
            if st.button("⏱️ Queue for 30-Min Human Approval", type="secondary", use_container_width=True):
                with st.spinner("Enqueuing post into 30-minute approval queue..."):
                    try:
                        q_item = queue_post_for_approval(
                            topic=st.session_state.topic or st.session_state.content.get("series_title", "Guide"),
                            format_type=st.session_state.carousel_mode,
                            slot="evening",
                            slide_paths=st.session_state.slide_paths,
                            caption=caption_val,
                            auto_comment=comment_val,
                            content_plan=st.session_state.content,
                            timeout_minutes=30,
                            upload_cdn_now=True,
                        )
                        st.success(f"🎉 Enqueued! Check the **⏱️ 30-Min Approval Queue** tab to review countdown and slides (ID: `{q_item['id']}`).")
                    except Exception as e:
                        st.error(f"Failed to queue post: {e}")

# ---------------------------------------------------------------------------
# Tab 4: Analytics & Supabase Feedback Loop
# ---------------------------------------------------------------------------
with tab_analytics:
    st.markdown("### 📈 Post-Publishing Analytics & Supabase Feedback Loop")
    st.markdown(
        "Fetches live Instagram post metrics via **Meta Graph API** after 24–48 hours. "
        "High-intent actions (**Saves × 3**, **Shares × 3**, **Comments × 2**, **Likes × 1**) calculate an "
        "**Engagement Score** that feeds back into the **5-Stage AI Topic Funnel**, injecting up to "
        "**+3.0 Historical Resonance Boost** into semantically related candidate topics."
    )

    # Fetch Supabase records and top performing topics
    all_supabase_posts = fetch_posts_from_supabase(limit=50)
    top_performers = get_top_performing_topics(min_score=20.0, limit=20)

    # Analytics Metrics Row
    a_col1, a_col2, a_col3, a_col4 = st.columns([1.2, 1.2, 1.2, 1])
    with a_col1:
        st.markdown(
            f'<div class="stat-pill"><div class="stat-val">{len(all_supabase_posts)}</div><div class="stat-lbl">Supabase Posts</div></div>',
            unsafe_allow_html=True,
        )
    with a_col2:
        st.markdown(
            f'<div class="stat-pill" style="border-color: #34d399;"><div class="stat-val" style="color: #34d399;">{len(top_performers)}</div><div class="stat-lbl">Active Winners</div></div>',
            unsafe_allow_html=True,
        )
    with a_col3:
        avg_score = 0.0
        if top_performers:
            avg_score = round(sum(p.get("engagement_score", 0.0) for p in top_performers) / len(top_performers), 1)
        st.markdown(
            f'<div class="stat-pill" style="border-color: #818cf8;"><div class="stat-val" style="color: #818cf8;">{avg_score}</div><div class="stat-lbl">Avg Winner Score</div></div>',
            unsafe_allow_html=True,
        )
    with a_col4:
        if st.button("🔄 Audit Insights Now", type="primary", use_container_width=True):
            with st.spinner("Fetching Graph API metrics & updating Supabase..."):
                audit_summary = audit_published_posts_insights(max_posts=20)
                st.success(f"Audit Complete! Updated {audit_summary.get('audited_count', 0)} posts. Found {audit_summary.get('top_performers_count', 0)} top performers.")
                st.rerun()

    st.markdown("---")

    # Interactive Resonance Simulator
    with st.expander("⚡ **Test Topic Resonance Boost in 5-Stage Funnel**", expanded=True):
        st.caption("Enter any topic to calculate its real-time semantic similarity against top-performing past posts and view the resulting Stage 5 Actionability Bonus.")
        sim_input = st.text_input("Candidate Topic", value=st.session_state.topic or "Modern Python Async Architecture Patterns")
        if sim_input:
            boost = calculate_topic_resonance_boost(sim_input)
            if boost > 0.0:
                st.markdown(
                    f"""
                    <div style="border-left: 4px solid #34d399; padding: 12px 18px; background: rgba(52,211,153,0.12); border-radius: 8px; margin-top: 8px;">
                        <strong style="color: #34d399; font-size: 1.1rem;">⚡ +{boost} Actionability Boost Earned!</strong>
                        <div style="color: #e2e8f0; font-size: 0.90rem; margin-top: 4px;">
                            This topic strongly matches historical high-engagement themes. In Stage 5 of the Funnel, its score will be boosted by <strong>+{boost}</strong>, elevating it to top priority.
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"""
                    <div style="border-left: 4px solid #94a3b8; padding: 12px 18px; background: rgba(148,163,184,0.10); border-radius: 8px; margin-top: 8px;">
                        <strong style="color: #cbd5e1; font-size: 1.0rem;">Neutral Resonance (+0.0 Boost)</strong>
                        <div style="color: #94a3b8; font-size: 0.88rem; margin-top: 4px;">
                            Topic will be judged purely on raw actionability steps (no historical engagement bias).
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.markdown("---")

    # Top Performing Posts (The Feed for Funnel Stage 5)
    st.markdown("### 🏆 Top Historical Performers Driving the AI Funnel")
    if not top_performers:
        st.info("No audited top performers yet. Click **'🔄 Audit Insights Now'** above to fetch metrics.")
    else:
        grid_cols = st.columns(2)
        for idx, p in enumerate(top_performers[:8]):
            target_col = grid_cols[idx % 2]
            score = p.get("engagement_score", 0.0)
            tier = "VIRAL_TIER" if score >= 100 else ("TOP_PERFORMER" if score >= 40 else "ABOVE_AVERAGE")
            tier_color = "#f43f5e" if tier == "VIRAL_TIER" else ("#fbbf24" if tier == "TOP_PERFORMER" else "#38bdf8")

            with target_col:
                st.markdown(
                    f"""
                    <div class="feed-card" style="border-color: rgba(129,140,248,0.35);">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                            <span class="funnel-step-badge badge-ai">{p.get('category', 'AI & CODING')}</span>
                            <span style="color: {tier_color}; font-weight: 800; font-size: 0.82rem; border: 1px solid {tier_color}; padding: 2px 8px; border-radius: 6px;">
                                {tier.replace('_', ' ')} • SCORE: {score}
                            </span>
                        </div>
                        <div class="feed-title">{p.get('title')}</div>
                        <div style="display: flex; gap: 16px; margin-top: 10px; font-size: 0.85rem; color: #cbd5e1;">
                            <span>💾 <strong>{p.get('saved', 0)}</strong> saves</span>
                            <span>↗️ <strong>{p.get('shares', 0)}</strong> shares</span>
                            <span>👀 <strong>{p.get('reach', 0)}</strong> reach</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    # Supabase Posts Explorer
    with st.expander("☁️ **Supabase Cloud Posts Database Explorer**", expanded=False):
        if not all_supabase_posts:
            st.info("No posts found in Supabase database.")
        else:
            for sp in all_supabase_posts[:15]:
                s_meta = sp.get("metadata") or {}
                s_insights = s_meta.get("insights") or {}
                s_score = s_insights.get("engagement_score", 0.0)
                slide_urls = s_meta.get("slide_urls") or []

                st.markdown(
                    f"""
                    <div style="border: 1px solid rgba(255,255,255,0.08); background: rgba(15,23,42,0.4); border-radius: 10px; padding: 12px 16px; margin-bottom: 10px;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <strong style="color: #f1f5f9; font-size: 0.95rem;">{sp.get('title')}</strong>
                            <span style="color: #4ade80; font-size: 0.82rem; font-weight: 700;">Score: {s_score}</span>
                        </div>
                        <div style="color: #94a3b8; font-size: 0.80rem; margin-top: 4px;">
                            Category: {sp.get('category')} | Format: {s_meta.get('format', 'carousel')} | Created: {sp.get('created_at')}
                        </div>
                        <div style="color: #cbd5e1; font-size: 0.82rem; margin-top: 6px; font-style: italic;">
                            "{sp.get('hook', 'No hook')}"
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if slide_urls:
                    th_cols = st.columns(min(len(slide_urls), 5))
                    for t_idx, u in enumerate(slide_urls[:5]):
                        with th_cols[t_idx]:
                            st.image(u, caption=f"Slide {t_idx+1}", use_container_width=True)

# ---------------------------------------------------------------------------
# Tab 5: Competitor Spy & AI Virality Reverse-Engineering
# ---------------------------------------------------------------------------
with tab_competitors:
    st.markdown("### 🕵️ Competitor Spy & AI Virality Reverse-Engineering")
    st.markdown(
        "Scrapes target Instagram competitor accounts using our optimized **Apify Engine** "
        "(12h cooldowns, 24h circuit breaker, 95% bandwidth savings). "
        "Multi-modal AI then reverse-engineers **why** competitor posts went viral (Hook Psychology, "
        "Slide Pacing, Caption Mechanics) and generates a **Vmatrix Adaptation Blueprint** to create "
        "an original 10x better carousel in our clean 100% white aesthetic."
    )

    if "competitor_handle" not in st.session_state:
        st.session_state.competitor_handle = "codewithharry"
    if "competitor_niche" not in st.session_state:
        st.session_state.competitor_niche = "AI & CODING"

    # Input controls
    c_col1, c_col2, c_col3 = st.columns([2, 1.5, 1])
    with c_col1:
        comp_handle_input = st.text_input(
            "Target Competitor Instagram Handle",
            value=st.session_state.competitor_handle,
            placeholder="e.g. codewithharry, ai.creators, daily_code",
        )
        st.session_state.competitor_handle = comp_handle_input.replace("@", "").strip()

    with c_col2:
        comp_niche_input = st.selectbox(
            "Niche Category",
            options=["AI & CODING", "TOOLS", "FINANCE"],
            index=0 if st.session_state.competitor_niche == "AI & CODING" else (1 if st.session_state.competitor_niche == "TOOLS" else 2),
        )
        st.session_state.competitor_niche = comp_niche_input

    with c_col3:
        comp_limit = st.slider("Max Posts", min_value=3, max_value=20, value=6, step=1)

    # Preset quick-buttons
    st.markdown("**Or pick a vetted niche competitor:**")
    comp_preset_cols = st.columns(4)
    COMP_PRESETS = [
        ("💻 @codewithharry", "codewithharry", "AI & CODING"),
        ("🤖 @ai.creators", "ai.creators", "AI & CODING"),
        ("⚡ @daily_code", "daily_code", "TOOLS"),
        ("💰 @levelsfyi", "levelsfyi", "FINANCE"),
    ]
    for p_idx, (lbl, h_val, n_val) in enumerate(COMP_PRESETS):
        with comp_preset_cols[p_idx]:
            if st.button(lbl, use_container_width=True, key=f"comp_pre_{p_idx}"):
                st.session_state.competitor_handle = h_val
                st.session_state.competitor_niche = n_val
                st.rerun()

    # Action buttons
    action_c1, action_c2 = st.columns([1.5, 3])
    with action_c1:
        scrape_btn = st.button("🚀 Scrape & Ingest Posts", type="primary", use_container_width=True)
    with action_c2:
        force_scrape = st.checkbox("Bypass 12h Cooldown (Force live scrape)", value=False)

    if scrape_btn:
        with st.spinner(f"Scraping latest posts for @{st.session_state.competitor_handle} via Apify / DB..."):
            scraper = InstaScraper()
            scraped_items = scraper.scrape(
                handle=st.session_state.competitor_handle,
                niche=st.session_state.competitor_niche,
                limit=comp_limit,
                force=force_scrape,
            )
            if scraped_items:
                st.success(f"Ingested {len(scraped_items)} posts for @{st.session_state.competitor_handle}!")
            else:
                st.info(f"Handle @{st.session_state.competitor_handle} is in cooldown (scraped recently) or returned 0 posts. Showing cached posts.")
            st.rerun()

    st.markdown("---")

    # Fetch stored competitor posts from database
    stored_posts = db.get_competitor_posts(
        handle=st.session_state.competitor_handle,
        niche=st.session_state.competitor_niche,
        limit=20,
    )
    if not stored_posts:
        # Also try fetching all competitor posts if specific handle has none
        stored_posts = db.get_competitor_posts(limit=20)

    # ---------------------------------------------------------------------------
    # Outlier Detection Engine (3-Gate Math + 7-Day Time Decay)
    # ---------------------------------------------------------------------------
    filter_col1, filter_col2, filter_col3 = st.columns([1.5, 1.5, 1])
    with filter_col1:
        mult_choice = st.radio("Outlier Threshold", options=["1.5x (Standard)", "3.0x (Strict)"], horizontal=True)
        mult_val = 3.0 if "3.0x" in mult_choice else 1.5

    with filter_col2:
        filter_outliers_only = st.checkbox("🔥 Show Only Viral Outliers (3-Gate Filter)", value=False)

    outlier_pipeline = detect_viral_outliers(stored_posts, multiplier_threshold=mult_val, min_cohort_size=3)
    outliers_list = outlier_pipeline["outliers"]
    all_evaluated = outlier_pipeline["all_evaluated"]
    reels_cohort = outlier_pipeline["cohorts"]["reels"]
    photos_cohort = outlier_pipeline["cohorts"]["photos"]

    # Display Cohort Mathematical Baselines
    stat_c1, stat_c2, stat_c3 = st.columns(3)
    with stat_c1:
        st.metric(
            label="🎬 Reels Cohort (Floor: 3k views)",
            value=f"{reels_cohort['count']} posts",
            delta="Active Baseline" if reels_cohort["valid"] else "Min 3 required (<3)",
        )
    with stat_c2:
        st.metric(
            label="📸 Photos Cohort (Floor: 500 likes)",
            value=f"{photos_cohort['count']} posts",
            delta="Active Baseline" if photos_cohort["valid"] else "Min 3 required (<3)",
        )
    with stat_c3:
        st.metric(
            label="🔥 Outliers Flagged",
            value=f"{len(outliers_list)} posts",
            delta=f"{len(outliers_list)}/{len(all_evaluated)} vetted",
        )

    posts_to_display = outliers_list if filter_outliers_only else all_evaluated

    st.markdown(f"### 📋 Competitor Posts & Reverse-Engineering Feed ({len(posts_to_display)} Displayed)")
    if not posts_to_display:
        if filter_outliers_only:
            st.info("No posts met all 3 outlier gates (1.5x median, 3k/500 floor, 1.0% ER) in this selection. Uncheck the filter above to view all posts.")
        else:
            st.info("No competitor posts ingested yet. Click **'🚀 Scrape & Ingest Posts'** above to fetch posts.")
    else:
        for idx, post in enumerate(posts_to_display):
            p_shortcode = post.get("shortcode", f"post_{idx}")
            p_handle = post.get("handle", "competitor")
            p_likes = post.get("likes", 0) or 0
            p_comments = post.get("comments", 0) or 0
            p_views = post.get("views", 0) or 0
            p_caption = post.get("caption", "")
            p_media = post.get("media_url", "")
            p_analysis = post.get("virality_analysis")
            is_outlier = post.get("is_outlier", False)
            v_score = post.get("virality_score", 0.0)
            raw_score = post.get("raw_score", 0.0)
            recency_mult = post.get("recency_multiplier", 1.0)
            age_days = post.get("age_days", 2.0)
            gate_1 = post.get("gate_1", {})
            gate_2 = post.get("gate_2", {})
            gate_3 = post.get("gate_3", {})

            # Outlier Badge Styling
            if is_outlier:
                tier_badge = f"🔥 {v_score:.1f}x VIRAL OUTLIER"
                tier_color = "#f43f5e"
                border_color = "rgba(244,63,94,0.4)"
            elif post.get("skip_reason"):
                tier_badge = f"⚪ {post.get('skip_reason', 'Standard')[:22]}"
                tier_color = "#94a3b8"
                border_color = "rgba(148,163,184,0.2)"
            else:
                tier_badge = f"📈 {raw_score:.1f}x Standard"
                tier_color = "#38bdf8"
                border_color = "rgba(56,189,248,0.2)"

            card_cls = "outlier-glow-card" if is_outlier else "feed-card"
            st.markdown(f'<div class="{card_cls}">', unsafe_allow_html=True)
            col_media, col_info = st.columns([1, 2.5])
            with col_media:
                if p_media:
                    st.image(p_media, use_container_width=True, caption=f"@{p_handle} ({p_shortcode})")
                else:
                    st.markdown(
                        f'<div style="background: rgba(30,41,59,0.5); border-radius: 12px; height: 160px; display: flex; align-items: center; justify-content: center; color: #94a3b8; font-weight: 600;">@{p_handle}</div>',
                        unsafe_allow_html=True,
                    )

            with col_info:
                st.markdown(
                    f"""
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <span style="font-weight: 800; color: #ffffff; font-size: 1.1rem; letter-spacing: -0.02em;">@{p_handle}</span>
                        <span style="color: {tier_color}; border: 1px solid {border_color}; padding: 4px 12px; border-radius: 999px; font-weight: 800; font-size: 0.82rem; background: rgba(15,23,42,0.6); box-shadow: 0 0 15px {border_color};">
                            {tier_badge}
                        </span>
                    </div>
                    <div style="font-size: 0.88rem; color: #cbd5e1; margin-bottom: 8px;">
                        ❤️ <strong>{p_likes:,}</strong> likes &nbsp;•&nbsp; 💬 <strong>{p_comments:,}</strong> comments &nbsp;•&nbsp; 👁️ <strong>{p_views:,}</strong> views
                    </div>
                    <div style="font-size: 0.84rem; color: #94a3b8; line-height: 1.45; margin-bottom: 12px; max-height: 75px; overflow: hidden;">
                        {p_caption[:240]}...
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                # 3-Gate Mathematical Diagnostics
                if gate_1 and gate_2 and gate_3:
                    with st.expander("📐 3-Gate Math & Virality Breakdown", expanded=is_outlier):
                        g1_icon = "✅" if gate_1.get("passed") else "❌"
                        g2_icon = "✅" if gate_2.get("passed") else "❌"
                        g3_icon = "✅" if gate_3.get("passed") else "❌"
                        st.markdown(
                            f"""
                            <div style="font-size: 0.82rem; line-height: 1.6; color: #cbd5e1; background: rgba(15,23,42,0.4); padding: 8px 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.06);">
                                <div><strong>{g1_icon} Gate 1 (Relative Multiplier):</strong> {gate_1.get('description', '')}</div>
                                <div><strong>{g2_icon} Gate 2 (Absolute Floor):</strong> {gate_2.get('description', '')}</div>
                                <div><strong>{g3_icon} Gate 3 (Composite ER >= 1%):</strong> {gate_3.get('description', '')}</div>
                                <div style="margin-top: 6px; padding-top: 6px; border-top: 1px solid rgba(255,255,255,0.1); color: #38bdf8;">
                                    <strong>📉 Time Decay:</strong> Raw {raw_score:.2f}x &times; Recency {recency_mult:.2f}x (at {age_days:.1f}d) = <strong style="color: #4ade80;">{v_score:.2f}x Virality Score</strong>
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                btn_c1, btn_c2 = st.columns([1.3, 1])
                with btn_c1:
                    if st.button(f"🧠 Analyze Virality", key=f"anlz_{p_shortcode}_{idx}", type="secondary", use_container_width=True):
                        with st.spinner("Reverse-engineering hook, slide structure & virality drivers with AI..."):
                            analysis_result = analyze_post_virality(post)
                            st.session_state[f"analysis_{p_shortcode}"] = analysis_result
                            st.rerun()

                with btn_c2:
                    st.markdown(
                        f'<a href="{post.get("post_url", "#")}" target="_blank" style="display: inline-block; padding: 7px 14px; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; color: #38bdf8; text-decoration: none; font-size: 0.84rem; font-weight: 600; text-align: center; width: 100%;">View on Instagram ↗</a>',
                        unsafe_allow_html=True,
                    )

            # Render AI Analysis breakdown if available
            cur_analysis = p_analysis or st.session_state.get(f"analysis_{p_shortcode}")
            if cur_analysis:
                h_info = cur_analysis.get("hook_analysis", {})
                p_info = cur_analysis.get("slide_pacing", {})
                c_info = cur_analysis.get("caption_mechanics", {})
                v_score_disp = cur_analysis.get("virality_score", 85)
                why_reasons = cur_analysis.get("why_it_went_viral", [])
                bp = cur_analysis.get("vmatrix_blueprint", {})

                st.markdown(
                    f"""
                    <div style="background: linear-gradient(135deg, rgba(15,23,42,0.85) 0%, rgba(30,27,75,0.5) 100%); border: 1px solid rgba(129,140,248,0.4); border-radius: 16px; padding: 20px 24px; margin-top: 14px; margin-bottom: 12px; box-shadow: 0 8px 30px rgba(0,0,0,0.4);">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
                            <span style="font-weight: 800; color: #818cf8; font-size: 1.1rem; letter-spacing: -0.02em;">🔬 AI Intelligence Dossier</span>
                            <span style="font-weight: 800; color: #4ade80; font-size: 1.0rem; background: rgba(74,222,128,0.15); border: 1px solid rgba(74,222,128,0.3); padding: 3px 10px; border-radius: 999px;">Score: {v_score_disp}/100</span>
                        </div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; font-size: 0.86rem;">
                            <div style="background: rgba(15,23,42,0.5); padding: 12px 14px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.06);">
                                <strong style="color: #f3f4f8;">🎯 Hook Psychology:</strong>
                                <div style="color: #cbd5e1; margin-top: 4px; line-height: 1.4;">{h_info.get('hook_breakdown', '')}</div>
                                <div style="color: #a78bfa; font-size: 0.80rem; margin-top: 6px;"><em>Trigger: {h_info.get('psychological_trigger', '')}</em></div>
                            </div>
                            <div style="background: rgba(15,23,42,0.5); padding: 12px 14px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.06);">
                                <strong style="color: #f3f4f8;">📊 Slide Pacing & Structure:</strong>
                                <div style="color: #cbd5e1; margin-top: 4px; line-height: 1.4;">{p_info.get('pacing_analysis', '')}</div>
                                <div style="color: #38bdf8; font-size: 0.80rem; margin-top: 6px;"><em>Density: {p_info.get('educational_density', '')}</em></div>
                            </div>
                        </div>
                        <div style="margin-top: 12px; font-size: 0.86rem; background: rgba(15,23,42,0.4); padding: 10px 14px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.06);">
                            <strong style="color: #f3f4f8;">📝 Caption Formula:</strong>
                            <div style="color: #cbd5e1; margin-top: 4px;">{c_info.get('cta_effectiveness', '')} • {c_info.get('save_share_triggers', '')}</div>
                        </div>
                        <div style="margin-top: 12px; font-size: 0.86rem;">
                            <strong style="color: #f3f4f8;">💡 Why It Went Viral:</strong>
                            <ul style="color: #cbd5e1; margin-top: 6px; padding-left: 20px; line-height: 1.5;">
                                {''.join(f'<li>{r}</li>' for r in why_reasons)}
                            </ul>
                        </div>
                        <div style="border-top: 1px solid rgba(255,255,255,0.12); margin-top: 14px; padding-top: 14px;">
                            <strong style="color: #34d399; font-size: 1.0rem;">🚀 Vmatrix Adaptation Blueprint:</strong>
                            <div style="color: #f8fafc; font-weight: 800; font-size: 1.05rem; margin-top: 4px;">"{bp.get('adapted_title', '')}"</div>
                            <div style="color: #94a3b8; font-style: italic; font-size: 0.86rem; margin-top: 2px;">Hook: {bp.get('hook_line', '')}</div>
                            <div style="color: #38bdf8; font-size: 0.82rem; margin-top: 4px;">Competitive Edge: {bp.get('competitive_advantage', '')}</div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                # Adapt for Vmatrix Button
                if st.button(f"⚡ Adapt into Vmatrix Carousel", key=f"adapt_{p_shortcode}_{idx}", type="primary", use_container_width=True):
                    adapted_title = bp.get("adapted_title") or f"Mastering {p_caption[:40]}"
                    target_fmt = bp.get("target_format", "listicle")
                    st.session_state.topic = adapted_title
                    st.session_state.carousel_mode = target_fmt
                    st.success(f"🎉 Adapted! Topic '{adapted_title}' loaded into Content Generator. Switch to Tab 2 to plan & render!")
                    st.balloons()

            st.markdown('</div>', unsafe_allow_html=True)
            st.markdown("<div style='margin-bottom: 8px;'></div>", unsafe_allow_html=True)



