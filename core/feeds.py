"""
core/feeds.py
-------------
Content & Topic Data Gathering Engine:
Fetches breaking search spikes, AI startup announcements, enterprise LLM research,
and trending developer tools across 4 core feeds:

1. 📈 Google Trends (India & Global search spikes)
2. 🤖 TechCrunch AI (AI startup & venture news)
3. 🏢 VentureBeat AI (Enterprise AI & foundation models)
4. 💻 Hacker News (Trending developer tools & open-source GitHub projects)

Built with multi-tier fallback resilience so rate limits or transient endpoint
downtimes never break the feed pipeline.
"""

import re
import html
import requests
import xml.etree.ElementTree as ET
from typing import List, Dict, Any

from .utils import retry_with_backoff, logger

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml,application/json;q=0.9,*/*;q=0.8",
}

TIMEOUT_SECONDS = 8


def _clean_html_text(raw_html: str | None) -> str:
    """Removes HTML tags, decodes HTML entities, and normalizes whitespace."""
    if not raw_html:
        return ""
    clean = re.sub(r"<[^>]+>", "", raw_html)
    clean = html.unescape(clean)
    return re.sub(r"\s+", " ", clean).strip()


# ---------------------------------------------------------------------------
# 1. 📈 Google Trends (IN & Global)
# ---------------------------------------------------------------------------
def fetch_google_trends(geo: str = "IN", max_items: int = 8) -> List[Dict[str, Any]]:
    """
    Fetches real-time search spikes from Google Trends RSS with fallback.
    """
    geo_code = (geo or "IN").upper()
    urls = [
        f"https://trends.google.com/trending/rss?geo={geo_code}",
        f"https://trends.google.com/trends/trendingsearches/daily/rss?geo={geo_code}",
    ]

    for url in urls:
        try:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=TIMEOUT_SECONDS)
            if resp.status_code != 200:
                continue

            root = ET.fromstring(resp.content)
            ns = {"ht": "https://trends.google.com/trending/rss"}
            results = []

            for item in root.findall(".//item"):
                if len(results) >= max_items:
                    break

                title_elem = item.find("title")
                title = _clean_html_text(title_elem.text if title_elem is not None else "")
                if not title:
                    continue

                traffic_elem = item.find("ht:approx_traffic", ns)
                traffic = traffic_elem.text if traffic_elem is not None else ""
                metric = f"🔥 {traffic} searches" if traffic else "🔥 Trending Search"

                desc_elem = item.find("description")
                desc = _clean_html_text(desc_elem.text if desc_elem is not None else "")

                link_elem = item.find("link")
                link = (
                    link_elem.text
                    if link_elem is not None and link_elem.text
                    else f"https://trends.google.com/trends/explore?q={title}&geo={geo_code}"
                )

                news_snippet = ""
                news_item = item.find("ht:news_item", ns)
                if news_item is not None:
                    news_title = news_item.find("ht:news_item_title", ns)
                    if news_title is not None and news_title.text:
                        news_snippet = _clean_html_text(news_title.text)

                summary = news_snippet or desc or f"Search spike trending in {geo_code}."
                if len(summary) > 140:
                    summary = summary[:137] + "..."

                results.append({
                    "source": f"Google Trends ({geo_code})",
                    "source_icon": "📈",
                    "title": title,
                    "summary": summary,
                    "metric": metric,
                    "url": link,
                    "category": "TRENDS",
                })

            if results:
                return results
        except Exception as e:
            logger.warning("Google Trends primary endpoint failed: %s", e)

    return []


# ---------------------------------------------------------------------------
# 2. 🤖 TechCrunch AI
# ---------------------------------------------------------------------------
def fetch_techcrunch_ai(max_items: int = 8) -> List[Dict[str, Any]]:
    """
    Fetches AI startup announcements, product launches, and venture rounds from TechCrunch AI.
    """
    endpoints = [
        ("https://techcrunch.com/category/artificial-intelligence/feed/", False),
        ("https://news.google.com/rss/search?q=site:techcrunch.com+AI&hl=en-US&gl=US&ceid=US:en", True),
    ]

    for url, is_gnews in endpoints:
        try:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=TIMEOUT_SECONDS)
            if resp.status_code != 200:
                continue

            root = ET.fromstring(resp.content)
            results = []

            for item in root.findall(".//item"):
                if len(results) >= max_items:
                    break

                title_elem = item.find("title")
                title = _clean_html_text(title_elem.text if title_elem is not None else "")
                if is_gnews and " - TechCrunch" in title:
                    title = title.replace(" - TechCrunch", "").strip()

                if not title:
                    continue

                link_elem = item.find("link")
                link = link_elem.text if link_elem is not None else ""

                desc_elem = item.find("description")
                desc = _clean_html_text(desc_elem.text if desc_elem is not None else "")
                if len(desc) > 140:
                    desc = desc[:137] + "..."

                results.append({
                    "source": "TechCrunch AI",
                    "source_icon": "🤖",
                    "title": title,
                    "summary": desc or "AI startup & venture news.",
                    "metric": "🤖 Startup & VC",
                    "url": link,
                    "category": "AI & CODING",
                })

            if results:
                return results
        except Exception as e:
            logger.warning("TechCrunch AI feed fetch error on %s: %s", url, e)

    return []


# ---------------------------------------------------------------------------
# 3. 🏢 VentureBeat AI
# ---------------------------------------------------------------------------
def fetch_venturebeat_ai(max_items: int = 8) -> List[Dict[str, Any]]:
    """
    Fetches enterprise AI models, LLM research, and foundation models from VentureBeat AI.
    Features automated failover to Google News RSS if Cloudflare rate limits.
    """
    endpoints = [
        ("https://news.google.com/rss/search?q=site:venturebeat.com+AI&hl=en-US&gl=US&ceid=US:en", True),
        ("https://venturebeat.com/category/ai/feed/", False),
    ]

    for url, is_gnews in endpoints:
        try:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=TIMEOUT_SECONDS)
            if resp.status_code != 200:
                continue

            root = ET.fromstring(resp.content)
            results = []

            for item in root.findall(".//item"):
                if len(results) >= max_items:
                    break

                title_elem = item.find("title")
                title = _clean_html_text(title_elem.text if title_elem is not None else "")
                if is_gnews and " - VentureBeat" in title:
                    title = title.replace(" - VentureBeat", "").strip()

                if not title:
                    continue

                link_elem = item.find("link")
                link = link_elem.text if link_elem is not None else ""

                desc_elem = item.find("description")
                desc = _clean_html_text(desc_elem.text if desc_elem is not None else "")
                if len(desc) > 140:
                    desc = desc[:137] + "..."

                results.append({
                    "source": "VentureBeat AI",
                    "source_icon": "🏢",
                    "title": title,
                    "summary": desc or "Enterprise AI models, LLMs, and research.",
                    "metric": "🏢 Enterprise AI",
                    "url": link,
                    "category": "AI & CODING",
                })

            if results:
                return results
        except Exception as e:
            logger.warning("VentureBeat AI feed fetch error on %s: %s", url, e)

    return []


# ---------------------------------------------------------------------------
# 4. 💻 Hacker News (Dev Tools & Open-Source)
# ---------------------------------------------------------------------------
def fetch_hacker_news(max_items: int = 8) -> List[Dict[str, Any]]:
    """
    Fetches trending developer tools, coding libraries, and open-source GitHub projects
    from Hacker News with Algolia API and RSS fallback.
    """
    # 1. Try Algolia Search API
    try:
        url = "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=25"
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=TIMEOUT_SECONDS)
        if resp.status_code == 200:
            data = resp.json()
            hits = data.get("hits", [])
            results = []

            for hit in hits:
                if len(results) >= max_items:
                    break

                title = hit.get("title")
                if not title:
                    continue

                points = hit.get("points") or 0
                comments = hit.get("num_comments") or 0
                link = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"

                metric = f"⭐ {points} pts · 💬 {comments}"
                summary = f"Trending developer topic on Hacker News ({points} upvotes, {comments} comments)."

                results.append({
                    "source": "Hacker News",
                    "source_icon": "💻",
                    "title": title,
                    "summary": summary,
                    "metric": metric,
                    "url": link,
                    "category": "TOOLS",
                })

            if results:
                return results
    except Exception as e:
        logger.warning("Hacker News Algolia API failed: %s", e)

    # 2. Fallback to HN RSS
    try:
        rss_url = "https://news.ycombinator.com/rss"
        resp = requests.get(rss_url, headers=DEFAULT_HEADERS, timeout=TIMEOUT_SECONDS)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            results = []
            for item in root.findall(".//item"):
                if len(results) >= max_items:
                    break
                title_elem = item.find("title")
                title = _clean_html_text(title_elem.text if title_elem is not None else "")
                link_elem = item.find("link")
                link = link_elem.text if link_elem is not None else ""
                if title:
                    results.append({
                        "source": "Hacker News",
                        "source_icon": "💻",
                        "title": title,
                        "summary": "Trending on Hacker News front page.",
                        "metric": "⭐ Trending on HN",
                        "url": link,
                        "category": "TOOLS",
                    })
            if results:
                return results
    except Exception as e:
        logger.warning("Hacker News RSS fallback failed: %s", e)

    return []


# ---------------------------------------------------------------------------
# Unified Aggregator
# ---------------------------------------------------------------------------
def fetch_all_feeds(geo: str = "IN", max_per_feed: int = 6) -> Dict[str, List[Dict[str, Any]]]:
    """
    Aggregates all 4 core data feeds into a unified dictionary.
    Safe: failures in any single feed are logged and returned gracefully.
    """
    return {
        "google_trends": fetch_google_trends(geo=geo, max_items=max_per_feed),
        "techcrunch_ai": fetch_techcrunch_ai(max_items=max_per_feed),
        "venturebeat_ai": fetch_venturebeat_ai(max_items=max_per_feed),
        "hacker_news": fetch_hacker_news(max_items=max_per_feed),
    }
