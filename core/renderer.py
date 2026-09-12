"""
core/renderer.py
-----------------
Renders Jinja2 HTML templates into crisp 1080x1350 (4:5 Instagram-vertical)
PNGs using headless Chromium via Playwright. This is what lets us design
slides with real CSS (grid, blur, gradients, web fonts) instead of fighting
Pillow's primitive drawing API.
"""

from pathlib import Path
from jinja2 import Environment, FileSystemLoader, ChoiceLoader

from playwright.sync_api import sync_playwright, Error as PlaywrightError

try:
    from pypdf import PdfMerger
except ImportError:
    from pypdf import PdfWriter as PdfMerger

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
from .logo_resolver import resolve_logo, resolve_logo_url

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
    env = Environment(
        loader=ChoiceLoader([
            FileSystemLoader(str(TEMPLATE_DIR)),
            FileSystemLoader(str(TEMPLATE_DIR / "listicle")),
        ]),
        autoescape=True,
    )
    env.filters["favicon"] = get_favicon_url
    env.filters["logo"] = get_logo_url
    env.filters["resolve_logo"] = resolve_logo_url
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
                temp_html = output_path.parent / f"_temp_{output_path.stem}.html"
                temp_html.write_text(html_content, encoding="utf-8")
                try:
                    page.goto(temp_html.absolute().as_uri(), wait_until="load", timeout=20000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=3000)
                    except Exception:
                        pass
                    page.wait_for_timeout(600)  # allow web fonts / favicons / gradients to settle

                    if img_format.lower() in ("jpg", "jpeg"):
                        page.screenshot(path=str(output_path), type="jpeg", quality=95)
                    else:
                        page.screenshot(path=str(output_path), type="png")

                    validate_slide_image(output_path, *EXPECTED_PNG_SIZE)
                    saved_paths.append(output_path)
                finally:
                    temp_html.unlink(missing_ok=True)
        finally:
            browser.close()

    return saved_paths


def render_carousel_slides(data: dict, output_dir: Path, image_format: str = "jpeg") -> list[Path]:
    """
    Renders all 5 educational listicle slides using the modern pure white theme (render_listicle_slides).
    Uses browser pooling and in-memory rendering (2160x2700 Retina).
    Enforces pure white aesthetic by default (theme="LIGHT").
    Returns list of saved image paths.
    """
    data.setdefault("theme", "LIGHT")
    return render_listicle_slides(data, output_dir, image_format=image_format)


def render_rich_flow_slides(flow_data: dict, output_dir: Path, image_format: str = "jpeg") -> list[Path]:
    """
    Renders carousel_flow.html templates to ultra-sharp 2160x2700 Retina PNGs/JPEGs
    and a compiled lead magnet PDF (full_carousel_guide.pdf).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    env = _get_jinja_env()
    template = env.get_template("carousel_flow.html")

    slides = flow_data.get("slides", [])
    total_slides = len(slides) + 1
    theme = flow_data.get("theme", "LIGHT")  # Or "DARK"
    cta_keyword = flow_data.get("cta_keyword", "GUIDE")
    brand_handle = flow_data.get("brand_handle", "@vmatrix.co")
    ext = "jpg" if image_format.lower() in ("jpg", "jpeg") else "png"

    pages: list[tuple[str, Path]] = []

    # ── A. Render Cover Slide HTML ──────────────────────────────────────────
    cover_html = template.render(
        is_cover=True,
        theme=theme,
        slide_index=1,
        total_slides=total_slides,
        cover_title=flow_data.get("cover_title", flow_data.get("title", "System Architecture Flow")),
        cover_subtitle=flow_data.get("cover_subtitle", flow_data.get("hook_line", "A beginner walkthrough")),
        tools=flow_data.get("tools", []),
        cta_keyword=cta_keyword,
        brand_handle=brand_handle,
    )
    pages.append((cover_html, output_dir / f"slide_1.{ext}"))

    # ── B. Render Content Flow Steps HTML ──────────────────────────────────
    for idx, s_data in enumerate(slides):
        diagram = s_data.get("diagram", {})
        if not diagram or not isinstance(diagram, dict):
            nodes_list = s_data.get("nodes", [])
            diagram = {
                "type": "flowchart",
                "nodes": [n.get("name", str(n)) if isinstance(n, dict) else str(n) for n in nodes_list] if nodes_list else ["Input", "Process", "Output"],
            }

        tools_list = s_data.get("tools", [])
        if not tools_list and flow_data.get("tools"):
            tools_list = flow_data.get("tools")

        slide_html = template.render(
            is_cover=False,
            theme=theme,
            slide_index=idx + 2,
            total_slides=total_slides,
            headline=s_data.get("headline", f"Phase 0{idx+1}: Architecture Flow"),
            description=s_data.get("description", ""),
            tools=tools_list,
            diagram=diagram,
            cta_keyword=cta_keyword,
            brand_handle=brand_handle,
        )
        pages.append((slide_html, output_dir / f"slide_{idx + 2}.{ext}"))

    # ── C. High-Res Playwright Capture ─────────────────────────────────────
    image_paths: list[Path] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--force-color-profile=srgb"])
        # device_scale_factor=2 gives a crisp 2160x2700 Retina image!
        context = browser.new_context(
            viewport={"width": SLIDE_WIDTH, "height": SLIDE_HEIGHT},
            device_scale_factor=DEVICE_SCALE_FACTOR,
        )
        page = context.new_page()

        merger = PdfMerger()

        for idx, (html_content, img_path) in enumerate(pages):
            temp_html = output_dir / f"temp_slide_{idx+1}.html"
            temp_html.write_text(html_content, encoding="utf-8")

            # Load slide
            page.goto(temp_html.absolute().as_uri(), timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            page.wait_for_timeout(800)  # Wait for Google Fonts & SimpleIcons SVG render

            # 1. Screenshot PNG / JPEG
            if ext in ("jpg", "jpeg"):
                page.screenshot(path=str(img_path), type="jpeg", quality=95)
            else:
                page.screenshot(path=str(img_path), type="png")

            validate_slide_image(img_path, *EXPECTED_PNG_SIZE)
            image_paths.append(img_path)

            # 2. PDF Page for lead magnet
            slide_pdf = img_path.with_suffix(".pdf")
            try:
                page.pdf(
                    path=str(slide_pdf),
                    print_background=True,
                    width="1080px",
                    height="1350px",
                    margin={"top": "0px", "right": "0px", "bottom": "0px", "left": "0px"},
                )
                merger.append(str(slide_pdf))
            except Exception as e:
                logger.debug("Slide PDF generation skipped: %s", e)

            # Cleanup temp html
            temp_html.unlink(missing_ok=True)

        browser.close()

        # Merge all into one PDF
        final_pdf_path = output_dir / "full_carousel_guide.pdf"
        try:
            merger.write(str(final_pdf_path))
            merger.close()
        except Exception as e:
            logger.warning("PDF guide generation note: %s", e)

        # Remove individual pdf pages
        for p_file in output_dir.glob("slide_*.pdf"):
            p_file.unlink(missing_ok=True)

    logger.info("Generated %d slides and guide at %s", len(image_paths), final_pdf_path)
    return image_paths


def render_carousel_flow_slides(flow_data: dict, output_dir: Path, image_format: str = "jpeg") -> list[Path]:
    """
    Renders System Architecture Flowchart Carousel using templates/carousel_flow.html.
    Maintains backwards compatibility while using the 2x Retina rich flow engine.
    """
    return render_rich_flow_slides(flow_data, output_dir, image_format=image_format)


def render_cheatsheet_slide(cheatsheet_data: dict, output_dir: Path, image_format: str = "jpeg") -> Path:
    """
    Renders single-page reference cheatsheet using templates/single_page_cheatsheet.html.
    Supports 2-column editorial layout, category cards, commands, and CTA pill.
    Returns saved Path.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    env = _get_jinja_env()
    template = env.get_template("single_page_cheatsheet.html")

    ext = "jpg" if image_format.lower() in ("jpg", "jpeg") else "png"
    out_path = output_dir / f"cheatsheet.{ext}"

    theme = cheatsheet_data.get("theme", "LIGHT")
    html = template.render(
        title=cheatsheet_data.get("title", "Developer Reference"),
        title_highlight=cheatsheet_data.get("title_highlight", ""),
        hook_line=cheatsheet_data.get("hook_line", ""),
        category=cheatsheet_data.get("category", "CORE ESSENTIALS"),
        brand_tag=cheatsheet_data.get("brand_tag", "VMATRIX // REFERENCE"),
        brand_handle=cheatsheet_data.get("brand_handle", "@vmatrix.co"),
        theme=theme,
        cta_keyword=cheatsheet_data.get("cta_keyword", "GUIDE"),
        categories=cheatsheet_data.get("categories", []),
        items=cheatsheet_data.get("items", []),
    )
    results = _render_html_batch([(html, out_path, image_format)])
    return results[0]


def render_infographic(data: dict, output_dir: Path, image_format: str = "jpeg") -> Path:
    """
    Renders single-page cheatsheet using templates/single_page_cheatsheet.html (or fallback single_infographic.html).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    env = _get_jinja_env()
    try:
        template = env.get_template("single_page_cheatsheet.html")
    except Exception:
        template = env.get_template("single_infographic.html")

    theme = data.get("theme", "LIGHT")
    html = template.render(
        title=data.get("title", "Developer Cheatsheet"),
        title_highlight=data.get("title_highlight", ""),
        hook_line=data.get("hook_line", ""),
        category=data.get("category", "TOOLS"),
        brand_tag=data.get("brand_tag", "VMATRIX // CHEAT SHEET"),
        brand_handle=data.get("brand_handle", "@vmatrix.co"),
        theme=theme,
        cta_keyword=data.get("cta_keyword", "GUIDE"),
        categories=data.get("categories", []),
        items=data.get("items", []),
    )

    ext = "jpg" if image_format.lower() in ("jpg", "jpeg") else "png"
    out_path = output_dir / f"infographic.{ext}"
    results = _render_html_batch([(html, out_path, image_format)])
    return results[0]


def render_comparison_slide(comparison_data: dict, output_dir: Path, image_format: str = "jpeg") -> Path:
    """
    Renders Paid vs. Free Comparison Slide using templates/listicle/comparison.html.
    Resolves official logos via 4-Tier logo resolver. Enforces pure white theme.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    env = _get_jinja_env()
    template = env.get_template("comparison.html")

    ext = "jpg" if image_format.lower() in ("jpg", "jpeg") else "png"
    out_path = output_dir / f"comparison.{ext}"

    paid_tool = comparison_data.get("paid_tool", "Proprietary Tool")
    paid_logo = comparison_data.get("paid_logo") or resolve_logo_url(
        paid_tool,
        domain=comparison_data.get("paid_domain", ""),
        output_dir=output_dir,
        suffix="paid",
    )

    free_tool = comparison_data.get("free_tool", "Open Source Alternative")
    free_logo = comparison_data.get("free_logo") or resolve_logo_url(
        free_tool,
        domain=comparison_data.get("free_domain", ""),
        output_dir=output_dir,
        suffix="free",
    )

    theme = comparison_data.get("theme", "LIGHT")
    html = template.render(
        title=comparison_data.get("title", f"{paid_tool} vs. {free_tool}"),
        slide_index=comparison_data.get("slide_index", 1),
        total_slides=comparison_data.get("total_slides", 1),
        brand_tag=comparison_data.get("brand_tag", "VMATRIX // TOOL SHOWDOWN"),
        brand_handle=comparison_data.get("brand_handle", "@vmatrix.co"),
        theme=theme,
        paid_tool=paid_tool,
        paid_price=comparison_data.get("paid_price", "$$$ PAID"),
        paid_desc=comparison_data.get("paid_desc", ""),
        paid_logo=paid_logo,
        free_tool=free_tool,
        free_price=comparison_data.get("free_price", "FREE / OSS"),
        free_desc=comparison_data.get("free_desc", ""),
        free_logo=free_logo,
    )
    results = _render_html_batch([(html, out_path, image_format)])
    return results[0]


def render_code_slide(code_data: dict, output_dir: Path, image_format: str = "jpeg") -> Path:
    """
    Renders VS Code Terminal / Editor slide using templates/listicle/listicle_code.html.
    Authentic dark macOS window on clean white background.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    env = _get_jinja_env()
    template = env.get_template("listicle_code.html")

    ext = "jpg" if image_format.lower() in ("jpg", "jpeg") else "png"
    out_path = output_dir / f"code_slide.{ext}"

    theme = code_data.get("theme", "LIGHT")
    html = template.render(
        title=code_data.get("title", "Command & Script Snippet"),
        slide_index=code_data.get("slide_index", 1),
        total_slides=code_data.get("total_slides", 1),
        brand_tag=code_data.get("brand_tag", "VMATRIX // CODE SNIPPET"),
        brand_handle=code_data.get("brand_handle", "@vmatrix.co"),
        theme=theme,
        filename=code_data.get("filename", "snippet.py"),
        code_content=code_data.get("code_content", "# Put code here"),
    )
    results = _render_html_batch([(html, out_path, image_format)])
    return results[0]


def render_listicle_slides(listicle_data: dict, output_dir: Path, image_format: str = "jpeg") -> list[Path]:
    """
    Renders a multi-slide listicle using the 5 templates:
    1. cover.html
    2. content.html
    3. comparison.html
    4. listicle_code.html
    5. outro.html
    Enforces pure white aesthetic by default (theme="LIGHT").
    Returns list of saved slide image paths.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    env = _get_jinja_env()
    slides = listicle_data.get("slides", [])
    total_slides = len(slides)
    theme = listicle_data.get("theme", "LIGHT")
    brand_handle = listicle_data.get("brand_handle", "@vmatrix.co")
    ext = "jpg" if image_format.lower() in ("jpg", "jpeg") else "png"

    html_items: list[tuple[str, Path, str]] = []
    for idx, slide in enumerate(slides, start=1):
        s_type = slide.get("type", "content").lower()
        s_theme = slide.get("theme", theme)

        if s_type == "cover":
            tpl = env.get_template("cover.html")
            items = slide.get("items") or slide.get("tools") or listicle_data.get("tools", [])
            if not items:
                items = []
                for s in slides:
                    if s.get("type") == "content":
                        t_name = s.get("tool_name") or s.get("name") or s.get("title", "")
                        d_name = s.get("tool_domain") or s.get("domain", "")
                        if t_name:
                            items.append({"name": t_name, "domain": d_name})

            subtitle_text = (
                slide.get("subtitle")
                or slide.get("hook_line")
                or listicle_data.get("subtitle")
                or listicle_data.get("hook_line")
                or "Complete Step-by-Step Breakdown"
            )
            html = tpl.render(
                title=slide.get("title", listicle_data.get("title", "Curated Tech Guide")),
                cover_title=slide.get("cover_title", listicle_data.get("title", "Curated Tech Guide")),
                subtitle=subtitle_text,
                cover_subtitle=subtitle_text,
                series_title=slide.get("series_title", listicle_data.get("series_title", "TECH GUIDE")),
                brand_tag=slide.get("brand_tag", listicle_data.get("brand_tag", "VMATRIX // CURATED GUIDE")),
                brand_handle=brand_handle,
                theme=s_theme,
                slide_index=idx,
                total_slides=total_slides,
                items=items,
                tools=items,
            )
        elif s_type in ("comparison", "vs"):
            tpl = env.get_template("comparison.html")
            paid_tool = slide.get("paid_tool", "Paid Tool")
            free_tool = slide.get("free_tool", "Free Tool")
            html = tpl.render(
                title=slide.get("title", f"{paid_tool} vs. {free_tool}"),
                paid_tool=paid_tool,
                paid_price=slide.get("paid_price", "$$$ PAID"),
                paid_desc=slide.get("paid_desc", ""),
                paid_logo=slide.get("paid_logo") or resolve_logo_url(paid_tool, domain=slide.get("paid_domain", ""), output_dir=output_dir, suffix=f"p_{idx}"),
                free_tool=free_tool,
                free_price=slide.get("free_price", "FREE / OSS"),
                free_desc=slide.get("free_desc", ""),
                free_logo=slide.get("free_logo") or resolve_logo_url(free_tool, domain=slide.get("free_domain", ""), output_dir=output_dir, suffix=f"f_{idx}"),
                brand_tag=slide.get("brand_tag", "VMATRIX // TOOL SHOWDOWN"),
                brand_handle=brand_handle,
                theme=s_theme,
                slide_index=idx,
                total_slides=total_slides,
            )
        elif s_type in ("code", "terminal"):
            tpl = env.get_template("listicle_code.html")
            html = tpl.render(
                title=slide.get("title", "Code Snippet"),
                filename=slide.get("filename", "main.py"),
                code_content=slide.get("code_content", "# Code snippet"),
                brand_tag=slide.get("brand_tag", "VMATRIX // CODE SNIPPET"),
                brand_handle=brand_handle,
                theme=s_theme,
                slide_index=idx,
                total_slides=total_slides,
            )
        elif s_type == "outro":
            tpl = env.get_template("outro.html")
            html = tpl.render(
                title=slide.get("title", "Want The Complete Source Repo?"),
                cta_keyword=slide.get("cta_keyword", listicle_data.get("cta_keyword", "GUIDE")),
                action_text=slide.get("action_text", ""),
                brand_tag=slide.get("brand_tag", "VMATRIX // ACTION REQUIRED"),
                brand_handle=brand_handle,
                theme=s_theme,
                slide_index=idx,
                total_slides=total_slides,
            )
        else:  # standard "content" slide
            tpl = env.get_template("content.html")
            tool_name = slide.get("tool_name") or slide.get("name", "")
            domain = slide.get("domain") or slide.get("tool_domain", "")
            tool_logo = slide.get("tool_logo") or slide.get("logo_url")
            if not tool_logo and tool_name:
                tool_logo = resolve_logo_url(tool_name, domain=domain, output_dir=output_dir, suffix=f"c_{idx}")
            step_num = slide.get("step_num") or f"{max(1, idx - 1):02d}"
            html = tpl.render(
                title=slide.get("title", tool_name),
                headline=slide.get("headline", ""),
                description=slide.get("description", ""),
                step_num=step_num,
                tool_name=tool_name,
                tool_logo=tool_logo,
                domain=domain,
                key_benefit=slide.get("key_benefit", ""),
                brand_tag=slide.get("brand_tag", "VMATRIX // TOOL SHOWCASE"),
                brand_handle=brand_handle,
                theme=s_theme,
                slide_index=idx,
                total_slides=total_slides,
            )

        out_path = output_dir / f"slide_{idx}.{ext}"
        html_items.append((html, out_path, image_format))

    return _render_html_batch(html_items)

