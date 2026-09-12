"""
competitor_analyzer.py
----------------------
Root export proxy for competitor virality analyzer.
"""
from core.competitor_analyzer import (
    analyze_post_virality,
    SYSTEM_PROMPT,
    VIRALITY_SCHEMA,
)

__all__ = [
    "analyze_post_virality",
    "SYSTEM_PROMPT",
    "VIRALITY_SCHEMA",
]
