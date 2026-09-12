"""
core/renderer.py
-----------------
Renders Jinja2 HTML templates into crisp 1080x1350 (4:5 Instagram-vertical)
PNGs using headless Chromium via Playwright. This is what lets us design
slides with real CSS (grid, blur, gradients, web fonts) instead of fighting
Pillow's primitive drawing API.
"""

from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from playwright.sync_api import sync_playwright, Error as PlaywrightError

from .utils import retry_with_backoff, validate_png, RenderValidationError, logger

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

SLIDE_WIDTH = 1080
SLIDE_HEIGHT = 1350
DEVICE_SCALE_FACTOR = 2  # crisp retina-grade output
EXPECTED_PNG_SIZE = (SLIDE_WIDTH * DEVICE_SCALE_FACTOR, SLIDE_HEIGHT * DEVICE_SCALE_FACTOR)


import os
import json
import urllib.request
from functools import lru_cache

@lru_cache(maxsize=256)
def resolve_brandfetch_logo(clean_domain: str) -> str | None:
    """Queries Brandfetch v2 API to resolve official brand icon/logo if available."""
    api_key = os.environ.get("BRANDFETCH_API_KEY")
    if not api_key:
        return None
    try:
        url = f"https://api.brandfetch.io/v2/brands/{clean_domain}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "ai-social-engine/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for logo in data.get("logos", []):
                if logo.get("type") in ("icon", "symbol", "logo"):
                    for fmt in logo.get("formats", []):
                        if fmt.get("src"):
                            return fmt.get("src")
    except Exception as e:
        logger.debug("Brandfetch lookup skipped for %s: %s", clean_domain, e)
    return None


def get_logo_url(domain: str) -> str:
    """
    Multi-tier high-res logo and icon resolver:
    1. 🚀 Logo.dev CDN (if LOGODEV_PUBLISHABLE_KEY or LOGODEV_SECRET_KEY is configured)
    2. 🏢 Brandfetch Brand API (if BRANDFETCH_API_KEY is configured)
    3. 🌐 Google Favicon high-res endpoint (100% free universal fallback)
    """
    if not domain:
        domain = "github.com"
    clean_domain = domain.replace("https://", "").replace("http://", "").split("/")[0].strip().lower()

    # Tier 1: Logo.dev (Ultra-fast CDN, returns crisp 128px PNG)
    logodev_token = os.environ.get("LOGODEV_PUBLISHABLE_KEY") or os.environ.get("LOGODEV_SECRET_KEY")
    if logodev_token:
        return f"https://img.logo.dev/{clean_domain}?token={logodev_token}&size=128&format=png"

    # Tier 2: Brandfetch v2 API
    if os.environ.get("BRANDFETCH_API_KEY"):
        bf_url = resolve_brandfetch_logo(clean_domain)
        if bf_url:
            return bf_url

    # Tier 3: Google Favicon service
    return f"https://s2.googleusercontent.com/s2/favicons?domain={clean_domain}&sz=128"


def get_favicon_url(domain: str) -> str:
    """Alias for backwards compatibility and Jinja template filter."""
    return get_logo_url(domain)


def format_title_gradient(title: str) -> str:
    """
    Wraps the key punchy phrase in the title with <span class="gradient-text">.
    If colon is present: wraps whatever comes after the colon.
    Otherwise: wraps the latter half / last 2-3 words.
    """
    if not title:
        return ""
    if "<span" in title:
        return title
    if ":" in title:
        parts = title.split(":", 1)
        return f'{parts[0]}: <span class="gradient-text">{parts[1].strip()}</span>'
    words = title.split()
    if len(words) <= 2:
        return f'<span class="gradient-text">{title}</span>'
    split_idx = max(1, len(words) // 2)
    return f'{" ".join(words[:split_idx])} <span class="gradient-text">{" ".join(words[split_idx:])}</span>'


def _get_jinja_env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    env.filters["favicon"] = get_favicon_url
    env.filters["logo"] = get_logo_url
    env.filters["title_gradient"] = format_title_gradient
    return env


from .utils import retry_with_backoff, validate_slide_image, RenderValidationError, logger

validate_png = validate_slide_image

@retry_with_backoff(max_attempts=3, base_delay=1.5, exceptions=(PlaywrightError, RenderValidationError, TimeoutError))
def _render_html_batch(
    html_items: list[tuple[str, Path, str]],
) -> list[Path]:
    """
    Renders a batch of HTML strings using a single pooled Chromium browser process.
    html_items: list of (html_content, output_path, image_format ['jpeg'|'png'])
    5x faster than launching Chromium per slide, zero temp file residue on disk.
    """
    saved_paths: list[Path] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--force-color-profile=srgb"])
        try:
            context = browser.new_context(
                viewport={"width": SLIDE_WIDTH, "height": SLIDE_HEIGHT},
                device_scale_factor=DEVICE_SCALE_FACTOR,
            )
            page = context.new_page()

            for html_content, output_path, img_format in html_items:
                page.set_content(html_content, wait_until="load", timeout=20000)
                page.wait_for_timeout(350)  # allow web fonts / favicons / gradients to settle

                if img_format.lower() in ("jpg", "jpeg"):
                    page.screenshot(path=str(output_path), type="jpeg", quality=95)
                else:
                    page.screenshot(path=str(output_path), type="png")

                validate_slide_image(output_path, *EXPECTED_PNG_SIZE)
                saved_paths.append(output_path)
        finally:
            browser.close()

    return saved_paths


def render_carousel_slides(data: dict, output_dir: Path, image_format: str = "jpeg") -> list[Path]:
    """
    Renders all 5 educational listicle slides using templates/carousel_slide.html.
    Uses browser pooling and in-memory rendering (2160x2700 Retina).
    Returns list of saved image paths.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    env = _get_jinja_env()
    template = env.get_template("carousel_slide.html")

    slides = data.get("slides", [])
    total = len(slides)
    ext = "jpg" if image_format.lower() in ("jpg", "jpeg") else "png"

    # Extract 3 content steps for cover slide preview anchor
    content_steps = [s for s in slides if s.get("type") == "content"]

    html_items: list[tuple[str, Path, str]] = []
    for idx, slide in enumerate(slides, start=1):
        html = template.render(
            slide=slide,
            steps=content_steps,
            series_title=data.get("series_title", ""),
            category=data.get("category", "TOOLS"),
            slide_index=idx,
            slide_total=total,
        )
        out_path = output_dir / f"slide_{idx}.{ext}"
        html_items.append((html, out_path, image_format))

    return _render_html_batch(html_items)


def render_carousel_flow_slides(flow_data: dict, output_dir: Path, image_format: str = "jpeg") -> list[Path]:
    """
    Renders 5-slide System Architecture Flowchart Carousel using templates/carousel_flow.html:
    1. Cover Slide: Blueprint title, hook, tech stack chips with Logo.dev icons
    2-4. Flow Diagram Slides: Connected architecture nodes, status pills, specs
    5. Outro Slide: Call-to-Action keyword trigger box
    Uses pooled Chromium instance for high-speed in-memory rendering.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    env = _get_jinja_env()
    template = env.get_template("carousel_flow.html")

    slides_data = flow_data.get("slides", [])
    total_slides = len(slides_data) + 2  # Cover + N flow slides + Outro
    ext = "jpg" if image_format.lower() in ("jpg", "jpeg") else "png"
    html_items: list[tuple[str, Path, str]] = []

    # 1. Cover Slide
    cover_html = template.render(
        is_cover=True,
        is_outro=False,
        slide_index=1,
        total_slides=total_slides,
        category=flow_data.get("category", "AI & CODING"),
        series_title=flow_data.get("series_title", "SYSTEM ARCHITECTURE"),
        cover_title=flow_data.get("cover_title", flow_data.get("title", "System Blueprint")),
        cover_subtitle=flow_data.get("cover_subtitle", flow_data.get("hook_line", "Step-by-step Technical Flow")),
        tools=flow_data.get("tools", []),
    )
    html_items.append((cover_html, output_dir / f"flow_slide_1.{ext}", image_format))

    # 2. Flow Diagram Content Slides
    for idx, s in enumerate(slides_data):
        slide_index = idx + 2
        slide_html = template.render(
            is_cover=False,
            is_outro=False,
            slide_index=slide_index,
            total_slides=total_slides,
            category=flow_data.get("category", "AI & CODING"),
            headline=s.get("headline", f"Phase {idx+1}: Pipeline Execution"),
            description=s.get("description", ""),
            active_node_name=s.get("active_node_name", ""),
            status_badge=s.get("status_badge", "ACTIVE"),
            nodes=s.get("nodes", []),
            bullets=s.get("bullets", []),
        )
        html_items.append((slide_html, output_dir / f"flow_slide_{slide_index}.{ext}", image_format))

    # 3. Outro CTA Slide
    outro = flow_data.get("outro", {})
    outro_html = template.render(
        is_cover=False,
        is_outro=True,
        slide_index=total_slides,
        total_slides=total_slides,
        category=flow_data.get("category", "AI & CODING"),
        series_title=flow_data.get("series_title", "COMPLETE BLUEPRINT"),
        title=outro.get("title", "Ready to Build This Pipeline?"),
        cta_keyword=outro.get("cta_keyword", flow_data.get("cta_keyword", "FLOW")),
        action_text=outro.get("action_text", "Drop 'FLOW' below and get the complete starter repo."),
    )
    html_items.append((outro_html, output_dir / f"flow_slide_{total_slides}.{ext}", image_format))

    return _render_html_batch(html_items)


def render_infographic(data: dict, output_dir: Path, image_format: str = "jpeg") -> Path:
    """
    Renders single-page cheatsheet using templates/single_infographic.html.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    env = _get_jinja_env()
    template = env.get_template("single_infographic.html")

    html = template.render(
        title=data.get("title", ""),
        hook_line=data.get("hook_line", ""),
        category=data.get("category", "TOOLS"),
        items=data.get("items", []),
    )

    ext = "jpg" if image_format.lower() in ("jpg", "jpeg") else "png"
    out_path = output_dir / f"infographic.{ext}"
    results = _render_html_batch([(html, out_path, image_format)])
    return results[0]
