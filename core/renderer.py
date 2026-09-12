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


def _get_jinja_env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    env.filters["favicon"] = get_favicon_url
    env.filters["logo"] = get_logo_url
    return env


@retry_with_backoff(max_attempts=3, base_delay=1.5, exceptions=(PlaywrightError, RenderValidationError, TimeoutError))
def _render_html_to_png(html_content: str, output_path: Path) -> Path:
    """
    Renders HTML to a PNG and self-heals in two ways:
      1. Uses wait_until="load" (not "networkidle") so a blocked/slow external
         resource — e.g. Google Fonts or a favicon behind a flaky network —
         can never hang the render indefinitely; fonts/icons that arrive late
         just fall back to the CSS font stack or the onerror monogram instead
         of stalling the whole pipeline.
      2. Validates the resulting PNG (right dimensions, not a blank frame)
         before handing it back, and retries the whole render (via the
         decorator) if the check fails — covering the class of bug where the
         browser silently paints a broken/empty page instead of raising.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--force-color-profile=srgb"])
        try:
            page = browser.new_page(
                viewport={"width": SLIDE_WIDTH, "height": SLIDE_HEIGHT},
                device_scale_factor=DEVICE_SCALE_FACTOR,
            )
            page.set_content(html_content, wait_until="load", timeout=20000)
            page.wait_for_timeout(300)  # allow web fonts / favicons to settle
            page.screenshot(path=str(output_path), type="png")
        finally:
            browser.close()

    validate_png(output_path, *EXPECTED_PNG_SIZE)
    return output_path


def render_carousel_slides(data: dict, output_dir: Path) -> list[Path]:
    """
    Renders all 5 slides using templates/carousel_slide.html.
    Viewport: width=1080, height=1350, device_scale_factor=2 (crisp Retina output).
    Returns list of saved PNG paths: [slide_1.png, slide_2.png, ..., slide_5.png].
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    env = _get_jinja_env()
    template = env.get_template("carousel_slide.html")

    slides = data.get("slides", [])
    total = len(slides)
    saved_paths: list[Path] = []

    for idx, slide in enumerate(slides, start=1):
        html = template.render(
            slide=slide,
            series_title=data.get("series_title", ""),
            category=data.get("category", "TOOLS"),
            slide_index=idx,
            slide_total=total,
        )
        out_path = output_dir / f"slide_{idx}.png"
        _render_html_to_png(html, out_path)
        saved_paths.append(out_path)

    return saved_paths


def render_infographic(data: dict, output_dir: Path) -> Path:
    """
    Renders single-page cheatsheet using templates/single_infographic.html.
    Returns the path to infographic.png.
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

    out_path = output_dir / "infographic.png"
    _render_html_to_png(html, out_path)
    return out_path
