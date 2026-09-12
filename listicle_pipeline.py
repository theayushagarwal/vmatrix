"""
listicle_pipeline.py
--------------------
Linguistic Multi-Slide Listicle Engine and 4-Tier Logo Resolver.

Provides:
- 5 Listicle Templates: cover.html, content.html, comparison.html, listicle_code.html, outro.html
- 4-Tier Logo Resolver (resolve_logo)
- Playwright 2x Retina capture engine with automated PDF creation
- 100% Pure White Theme design aesthetic (Linear/Vercel styling)
"""

import os
import hashlib
import tempfile
import requests
from pathlib import Path
from typing import Optional, Tuple, Callable, List, Dict, Any

from core.logo_resolver import (
    resolve_logo,
    resolve_logo_url,
    SIMPLEICONS_ALIASES,
    DOMAIN_FALLBACKS,
)
from core.renderer import (
    render_comparison_slide,
    render_code_slide,
    render_listicle_slides,
    render_rich_flow_slides,
    render_cheatsheet_slide,
    SLIDE_WIDTH,
    SLIDE_HEIGHT,
    DEVICE_SCALE_FACTOR,
)


def render_paid_vs_free_showdown(
    paid_tool: str,
    free_tool: str,
    output_dir: Path,
    title: Optional[str] = None,
    paid_price: str = "$$$ PAID",
    paid_desc: str = "",
    paid_domain: str = "",
    free_price: str = "FREE / OSS",
    free_desc: str = "",
    free_domain: str = "",
    theme: str = "LIGHT",
    image_format: str = "jpeg",
) -> Path:
    """
    Renders our highest-performing listicle slide format:
    Pits an expensive paid tool against an open-source/free alternative.
    """
    data = {
        "title": title or f"{paid_tool} vs. {free_tool}",
        "paid_tool": paid_tool,
        "paid_price": paid_price,
        "paid_desc": paid_desc,
        "paid_domain": paid_domain,
        "free_tool": free_tool,
        "free_price": free_price,
        "free_desc": free_desc,
        "free_domain": free_domain,
        "theme": theme,
    }
    return render_comparison_slide(data, output_dir, image_format=image_format)


def render_code_snippet_slide(
    title: str,
    code_content: str,
    output_dir: Path,
    filename: str = "snippet.py",
    theme: str = "LIGHT",
    image_format: str = "jpeg",
) -> Path:
    """
    Renders authentic dark macOS window with syntax-highlighted code on clean white background.
    """
    data = {
        "title": title,
        "code_content": code_content,
        "filename": filename,
        "theme": theme,
    }
    return render_code_slide(data, output_dir, image_format=image_format)


def render_listicle_carousel(
    listicle_data: Dict[str, Any],
    output_dir: Path,
    image_format: str = "jpeg",
) -> List[Path]:
    """
    Full 5-template listicle carousel renderer (cover, content, comparison, code, outro).
    Enforces 100% white aesthetic by default.
    """
    if "theme" not in listicle_data:
        listicle_data["theme"] = "LIGHT"
    return render_listicle_slides(listicle_data, output_dir, image_format=image_format)


__all__ = [
    "resolve_logo",
    "resolve_logo_url",
    "render_paid_vs_free_showdown",
    "render_code_snippet_slide",
    "render_listicle_carousel",
    "render_comparison_slide",
    "render_code_slide",
    "render_listicle_slides",
]
