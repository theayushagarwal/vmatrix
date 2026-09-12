"""
media_generator.py
------------------
Root re-export for Layers 3, 4, and 5 QA:
- has_border_bleed
- validate_image_via_groq
- validate_image_via_nvidia
- validate_image_via_github
- validate_image
- shorten_slide_text
- verify_compiled_slides_vision
"""

from core.media_generator import (
    has_border_bleed,
    validate_image_via_groq,
    validate_image_via_nvidia,
    validate_image_via_github,
    validate_image,
    shorten_slide_text,
    verify_compiled_slides_vision,
)

__all__ = [
    "has_border_bleed",
    "validate_image_via_groq",
    "validate_image_via_nvidia",
    "validate_image_via_github",
    "validate_image",
    "shorten_slide_text",
    "verify_compiled_slides_vision",
]
