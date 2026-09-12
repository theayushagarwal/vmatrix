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
    render_carousel_slides,
    render_infographic,
    upload_images_to_cloudinary,
    publish_to_instagram_carousel,
    fetch_all_feeds,
    fetch_google_trends,
    fetch_techcrunch_ai,
    fetch_venturebeat_ai,
    fetch_hacker_news,
    run_filtering_funnel,
    record_post,
    get_recent_posts,
)

load_dotenv()

# ---------------------------------------------------------------------------
# Page config + custom styling
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="ai-social-engine",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .stApp { background: #090d16; color: #f3f4f8; }
    section[data-testid="stSidebar"] { background: #0d1220; border-right: 1px solid rgba(129,140,248,0.15); }
    .block-container { padding-top: 2.2rem; max-width: 1200px; }
    h1, h2, h3 { font-weight: 800 !important; letter-spacing: -0.02em; }
    .status-pill {
        display: inline-flex; align-items: center; gap: 8px;
        padding: 6px 14px; border-radius: 999px; font-size: 0.82rem; font-weight: 600;
        margin-bottom: 6px;
    }
    .status-ok { background: rgba(74,222,128,0.12); color: #4ade80; border: 1px solid rgba(74,222,128,0.3); }
    .status-missing { background: rgba(248,113,113,0.12); color: #f87171; border: 1px solid rgba(248,113,113,0.3); }
    
    .feed-card {
        background: rgba(30,41,59,0.45);
        border: 1px solid rgba(129,140,248,0.22);
        border-radius: 16px;
        padding: 18px 20px;
        margin-bottom: 12px;
        transition: transform 0.15s ease, border-color 0.15s ease;
    }
    .feed-card:hover {
        border-color: rgba(129,140,248,0.45);
    }
    .feed-title {
        font-size: 1.05rem;
        font-weight: 700;
        color: #f3f4f8;
        line-height: 1.35;
        margin-bottom: 6px;
    }
    .feed-summary {
        font-size: 0.88rem;
        color: #94a3b8;
        line-height: 1.4;
        margin-bottom: 10px;
    }
    .feed-meta {
        display: flex;
        align-items: center;
        gap: 12px;
        font-size: 0.80rem;
        color: #818cf8;
        font-weight: 600;
    }

    .funnel-card {
        background: linear-gradient(135deg, rgba(30,41,59,0.7) 0%, rgba(15,23,42,0.85) 100%);
        border: 1px solid rgba(129,140,248,0.35);
        border-radius: 18px;
        padding: 22px 24px;
        margin-bottom: 16px;
    }
    .funnel-step-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 999px;
        font-size: 0.76rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        margin-bottom: 8px;
    }
    .badge-ai { background: rgba(129,140,248,0.18); color: #818cf8; border: 1px solid rgba(129,140,248,0.4); }
    .badge-fin { background: rgba(52,211,153,0.18); color: #34d399; border: 1px solid rgba(52,211,153,0.4); }
    .badge-tools { background: rgba(56,189,248,0.18); color: #38bdf8; border: 1px solid rgba(56,189,248,0.4); }

    .stat-pill {
        background: rgba(15,23,42,0.6);
        border: 1px solid rgba(129,140,248,0.2);
        border-radius: 12px;
        padding: 10px 14px;
        text-align: center;
    }
    .stat-val { font-size: 1.3rem; font-weight: 800; color: #818cf8; }
    .stat-lbl { font-size: 0.72rem; color: #94a3b8; font-weight: 600; text-transform: uppercase; }

    div[data-testid="stImage"] img { border-radius: 18px; border: 1px solid rgba(129,140,248,0.2); }
    </style>
    """,
    unsafe_allow_html=True,
)

PRESETS = [
    "🔥 5 Claude Prompt Hacks",
    "⚡ Git Commands for Vibe Coders",
    "💰 S&P 500 Indexing Simplified",
]

# ---------------------------------------------------------------------------
# Sidebar: credential status & memory stats
# ---------------------------------------------------------------------------
def _status_row(label: str, ok: bool):
    cls = "status-ok" if ok else "status-missing"
    icon = "●" if ok else "○"
    st.sidebar.markdown(
        f'<div class="status-pill {cls}">{icon} {label}</div>', unsafe_allow_html=True
    )

recent_posts = get_recent_posts(days=30)

with st.sidebar:
    st.markdown("### ⚡ ai-social-engine")
    st.caption("Autonomous social media engine in < 5s")
    st.markdown("---")
    st.markdown("**System status**")
    _status_row("Groq (gpt-oss-120b)", bool(os.environ.get("GROQ_API_KEY")))
    _status_row("Logo.dev (Logos/Icons)", bool(os.environ.get("LOGODEV_PUBLISHABLE_KEY") or os.environ.get("LOGODEV_SECRET_KEY")))
    _status_row("Brandfetch API", bool(os.environ.get("BRANDFETCH_API_KEY")))
    _status_row("Supabase Cloud", bool(os.environ.get("SUPABASE_URL") and (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY"))))
    _status_row("Cloudinary", bool(os.environ.get("CLOUDINARY_CLOUD_NAME") and os.environ.get("CLOUDINARY_API_KEY")))
    _status_row("Instagram Live", bool(os.environ.get("IG_USER_ID") and os.environ.get("IG_ACCESS_TOKEN")))
    if os.environ.get("GEMINI_API_KEY"):
        _status_row("Gemini API (Fallback)", True)
    st.markdown("---")
    st.markdown("**5-Stage Funnel**")
    st.caption("🔴 Stage 1: Blacklist ($0, 0ms)")
    st.caption("🟢 Stage 2: Niche Scoring ($0, 1ms)")
    st.caption("🧠 Stage 3: Groq openai/gpt-oss-120b")
    st.caption("🔄 Stage 4: Vector Anti-Dup (Cosine)")
    st.caption("🏆 Stage 5: Format Fit & Actionability")
    st.markdown("---")
    st.markdown("**Post Memory (Last 30d)**")
    st.caption(f"💾 {len(recent_posts)} topics tracked for vector deduplication")
    st.markdown("---")
    st.caption("Missing a key? Add it to your `.env` file and restart the app.")

# ---------------------------------------------------------------------------
# Session state
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

# ---------------------------------------------------------------------------
# Feed Caching
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def load_cached_feeds(geo: str):
    return fetch_all_feeds(geo=geo, max_per_feed=15)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown("# ⚡ ai-social-engine")
st.markdown(
    "Turn breaking raw trends into high-converting Instagram carousels via our **5-Stage Filtering Funnel**, "
    "**Groq (openai/gpt-oss-120b)** structured planner, **Logo.dev** brand assets, and **Playwright 4K** renderer."
)

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

    if st.session_state.funnel_results:
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
# Topic Input + Presets
# ---------------------------------------------------------------------------
topic_col, _ = st.columns([3, 1])
with topic_col:
    topic_input = st.text_input(
        "Topic",
        value=st.session_state.topic,
        placeholder="e.g. 5 Claude Prompt Hacks for Developers or pick from the Funnel/Radar above",
        label_visibility="collapsed",
    )

st.markdown("**Or start from a preset:**")
preset_cols = st.columns(3)
for i, preset in enumerate(PRESETS):
    with preset_cols[i]:
        if st.button(preset, use_container_width=True):
            topic_input = preset.split(" ", 1)[1]
            st.session_state.topic = topic_input

st.session_state.topic = topic_input or st.session_state.topic

generate_clicked = st.button("✨ Generate Carousel", type="primary", use_container_width=True)

st.markdown("---")

tab_content, tab_preview, tab_publish = st.tabs(
    ["📋 Content Generation", "🖼️ Visual Carousel Preview", "🚀 Live Publishing"]
)

# ---------------------------------------------------------------------------
# Generation flow
# ---------------------------------------------------------------------------
if "last_failed_stage" not in st.session_state:
    st.session_state.last_failed_stage = None
if "pending_content" not in st.session_state:
    st.session_state.pending_content = None

def run_pipeline(topic: str, skip_generate: bool = False):
    """
    Runs generate -> render as one pipeline with stage tracking.
    """
    progress = st.progress(0, text="Initializing Groq (openai/gpt-oss-120b)…")
    content = st.session_state.pending_content if skip_generate else None

    if content is None:
        try:
            progress.progress(20, text="Planning structured carousel with Groq…")
            content = generate_carousel_content(topic)
            st.session_state.pending_content = content
        except Exception as e:
            st.session_state.last_failed_stage = "generate"
            progress.empty()
            st.error(
                f"**Content generation failed**: {e}\n\n"
                "This step retries transient failures automatically — "
                "if it still failed, check your `GROQ_API_KEY` in `.env`."
            )
            return

    try:
        progress.progress(55, text="Rendering slides with Playwright…")
        tmp_dir = Path(tempfile.mkdtemp(prefix="ai-social-"))
        slide_paths = render_carousel_slides(content, tmp_dir)

        progress.progress(100, text="Done.")
        st.session_state.content = content
        st.session_state.slide_paths = slide_paths
        st.session_state.last_failed_stage = None
        st.session_state.pending_content = None

        # Automatically record to 30-day post history memory for deduplication
        record_post(
            title=content.get("series_title") or topic,
            category=content.get("category", "AI & CODING"),
            hook=content.get("hook_line", ""),
        )

        st.success(f"Generated \"{content.get('series_title', 'your carousel')}\" — 5 slides ready & recorded to memory.")
    except Exception as e:
        st.session_state.last_failed_stage = "render"
        progress.empty()
        st.error(
            f"**Slide rendering failed** (Playwright): {e}\n\n"
            "Each slide render is retried automatically and checked for a "
            "blank/broken frame before being accepted — this means every "
            "retry also failed the same way. The content plan itself was "
            "generated successfully and won't be regenerated on retry."
        )


if generate_clicked:
    if not st.session_state.topic.strip():
        st.warning("Enter a topic first or pick one from the Funnel/Radar above.")
    else:
        st.session_state.pending_content = None
        run_pipeline(st.session_state.topic)

if st.session_state.last_failed_stage == "generate":
    if st.button("🔁 Retry content generation", use_container_width=True):
        run_pipeline(st.session_state.topic)
elif st.session_state.last_failed_stage == "render":
    if st.button("🔁 Retry rendering (reuses existing content plan)", use_container_width=True):
        run_pipeline(st.session_state.topic, skip_generate=True)

# ---------------------------------------------------------------------------
# Tab 1: structured JSON
# ---------------------------------------------------------------------------
with tab_content:
    if st.session_state.content:
        st.markdown(f"### {st.session_state.content.get('series_title', '')}")
        st.caption(st.session_state.content.get("hook_line", ""))
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
        st.text_area(
            "caption",
            value=st.session_state.content.get("caption", ""),
            height=150,
            label_visibility="collapsed",
        )

        if st.button("🚀 Publish to Instagram Live", type="primary", use_container_width=True):
            pub_progress = st.progress(0, text="Uploading slides to Cloudinary…")
            try:
                image_urls = upload_images_to_cloudinary(st.session_state.slide_paths)
                pub_progress.progress(35, text="Creating carousel item containers…")

                pub_progress.progress(60, text="Waiting for Instagram to process containers…")
                result = publish_to_instagram_carousel(
                    image_urls, st.session_state.content.get("caption", "")
                )

                pub_progress.progress(100, text="Published.")
                st.success(f"🎉 Live on Instagram — post ID `{result['post_id']}`")
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
