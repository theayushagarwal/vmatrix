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


def get_favicon_url(domain: str) -> str:
    """Returns Google's free high-res favicon URL for any domain."""
    if not domain:
        return "https://s2.googleusercontent.com/s2/favicons?domain=github.com&sz=128"
    clean_domain = domain.replace("https://", "").replace("http://", "").split("/")[0]
    return f"https://s2.googleusercontent.com/s2/favicons?domain={clean_domain}&sz=128"


def _get_jinja_env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    env.filters["favicon"] = get_favicon_url
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
