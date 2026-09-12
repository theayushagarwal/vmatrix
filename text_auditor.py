"""
text_auditor.py
---------------
Root re-export for Layer 1 & 2 Caption & Text Compliance Auditor.
"""

from core.text_auditor import (
    verify_text_content,
    validate_caption,
    auto_fix_caption,
)

__all__ = [
    "verify_text_content",
    "validate_caption",
    "auto_fix_caption",
]
