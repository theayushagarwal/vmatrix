"""
analytics.py
------------
Root re-export for Post-Publishing Analytics & Meta Graph API Insights Engine.
"""

from core.analytics import (
    calculate_engagement_score,
    classify_resonance_tier,
    fetch_instagram_post_insights,
    audit_published_posts_insights,
)

__all__ = [
    "calculate_engagement_score",
    "classify_resonance_tier",
    "fetch_instagram_post_insights",
    "audit_published_posts_insights",
]
