"""
llm_utils.py
------------
Root re-export for LLM utility functions and compliance definitions.
"""

from core.llm_utils import (
    DISCLAIMER,
    BRAND_SYSTEM_PROMPT,
    FORBIDDEN_HASHTAGS,
    SHADOWBAN_TRIGGER_PHRASES,
    passes_shadowban_check,
    call_secondary_brain,
)

__all__ = [
    "DISCLAIMER",
    "BRAND_SYSTEM_PROMPT",
    "FORBIDDEN_HASHTAGS",
    "SHADOWBAN_TRIGGER_PHRASES",
    "passes_shadowban_check",
    "call_secondary_brain",
]
