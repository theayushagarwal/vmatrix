"""
app.py
-------
Streamlit demo UI for ai-social-engine:
1. Discover breaking trends across 4 core data feeds (Google Trends, TechCrunch AI, VentureBeat AI, Hacker News).
2. Gemini 2.5 Flash plans a high-converting structured carousel.
3. Playwright renders it into on-brand 4:5 Retina slides.
4. Cloudinary + Meta Graph API publishes it straight to Instagram.
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
# Sidebar: credential status
# ---------------------------------------------------------------------------
def _status_row(label: str, ok: bool):
    cls = "status-ok" if ok else "status-missing"
    icon = "●" if ok else "○"
    st.sidebar.markdown(
        f'<div class="status-pill {cls}">{icon} {label}</div>', unsafe_allow_html=True
    )

with st.sidebar:
    st.markdown("### ⚡ ai-social-engine")
    st.caption("Autonomous social media engine in < 5s")
    st.markdown("---")
    st.markdown("**System status**")
    _status_row("Gemini API", bool(os.environ.get("GEMINI_API_KEY")))
    _status_row("Cloudinary", bool(os.environ.get("CLOUDINARY_CLOUD_NAME") and os.environ.get("CLOUDINARY_API_KEY")))
    _status_row("Instagram", bool(os.environ.get("IG_USER_ID") and os.environ.get("IG_ACCESS_TOKEN")))
    st.markdown("---")
    st.markdown("**Core Data Feeds**")
    st.caption("📈 Google Trends (IN & Global)")
    st.caption("🤖 TechCrunch AI (Startups)")
    st.caption("🏢 VentureBeat AI (Enterprise)")
    st.caption("💻 Hacker News (Dev Tools)")
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

# ---------------------------------------------------------------------------
# Feed Caching
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def load_cached_feeds(geo: str):
    return fetch_all_feeds(geo=geo, max_per_feed=6)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown("# ⚡ ai-social-engine")
st.markdown(
    "Discover breaking topics from **4 live feeds**, let Gemini plan the structured carousel, "
    "render 4K Retina slides with Playwright, and publish straight to Instagram."
)

# ---------------------------------------------------------------------------
# Section: 📡 Real-Time Topic Radar (4 Core Data Feeds)
# ---------------------------------------------------------------------------
with st.expander("📡 **Real-Time Topic Radar (4 Core Feeds)** — Click any trending topic to load it", expanded=True):
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

        # Render in a 2-column grid
        col1, col2 = st.columns(2)
        for idx, item in enumerate(items):
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
        placeholder="e.g. 5 Claude Prompt Hacks for Developers or pick from the Radar above",
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
    progress = st.progress(0, text="Warming up Gemini 2.5 Flash…")
    content = st.session_state.pending_content if skip_generate else None

    if content is None:
        try:
            progress.progress(20, text="Planning carousel structure…")
            content = generate_carousel_content(topic)
            st.session_state.pending_content = content
        except Exception as e:
            st.session_state.last_failed_stage = "generate"
            progress.empty()
            st.error(
                f"**Content generation failed** (Gemini): {e}\n\n"
                "This step already retries transient failures automatically — "
                "if it still failed, check `GEMINI_API_KEY` and your quota."
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
        st.success(f"Generated \"{content.get('series_title', 'your carousel')}\" — 5 slides ready.")
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
        st.warning("Enter a topic first or pick one from the Real-Time Topic Radar above.")
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
