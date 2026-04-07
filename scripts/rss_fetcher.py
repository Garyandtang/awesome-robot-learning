"""Fetch RSS/Atom feeds and normalize entries to standard paper metadata."""

from datetime import datetime, timedelta

import feedparser
import requests
import trafilatura


def parse_feed_entries(feed_text: str) -> list[dict]:
    """Parse RSS/Atom feed text and return list of raw entry dicts."""
    feed = feedparser.parse(feed_text)
    entries = []
    for entry in feed.entries:
        link = entry.get("link", "")
        if not link:
            links = entry.get("links", [])
            for lnk in links:
                if lnk.get("rel") == "alternate":
                    link = lnk.get("href", "")
                    break
        published = entry.get("published", entry.get("updated", ""))
        summary = entry.get("summary", entry.get("description", ""))
        author = ""
        if entry.get("authors"):
            author = entry.authors[0].get("name", "")
        elif entry.get("author"):
            author = entry.author

        entries.append({
            "title": entry.get("title", "").replace("\n", " ").strip(),
            "url": link,
            "published": published,
            "summary": summary.strip() if summary else "",
            "author": author,
        })
    return entries


def _parse_date(date_str: str) -> datetime | None:
    """Try to parse a date string from RSS into a datetime."""
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.replace(tzinfo=None) if dt.tzinfo else dt
        except ValueError:
            continue
    return None


def normalize_rss_entry(raw: dict, feed_config: dict) -> dict:
    """Normalize a raw RSS entry to the standard paper metadata format."""
    date_str = ""
    parsed_dt = _parse_date(raw.get("published", ""))
    if parsed_dt:
        date_str = f"{parsed_dt.year}.{parsed_dt.month:02d}"

    return {
        "title": raw.get("title", ""),
        "authors": [raw["author"]] if raw.get("author") else [],
        "abstract": raw.get("summary", ""),
        "url": raw.get("url", ""),
        "pdf_url": "",
        "venue": "blog",
        "date": date_str,
        "arxiv_id": "",
        "project_url": None,
        "has_code": False,
        "source_type": "rss",
        "source_name": feed_config.get("name", ""),
        "full_text": None,
    }


def _make_seen_key(entry: dict) -> str:
    """Generate a dedup key for an RSS entry."""
    return f"rss:{entry.get('url', entry.get('title', ''))}"


def fetch_all_feeds(
    feeds: list[dict],
    seen: dict,
    days_back: int = 7,
) -> list[dict]:
    """Fetch all configured RSS feeds, normalize and deduplicate."""
    cutoff = datetime.utcnow() - timedelta(days=days_back)
    results = []

    for feed_cfg in feeds:
        url = feed_cfg.get("url", "")
        if not url:
            continue
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
        except (requests.RequestException, Exception):
            continue

        raw_entries = parse_feed_entries(resp.text)
        for raw in raw_entries:
            parsed_dt = _parse_date(raw.get("published", ""))
            if parsed_dt and parsed_dt < cutoff:
                continue

            normalized = normalize_rss_entry(raw, feed_cfg)
            seen_key = _make_seen_key(normalized)
            if seen_key in seen:
                continue

            results.append(normalized)

    return results


def fetch_full_text(url: str, timeout: int = 30) -> str | None:
    """Extract full text from a blog post URL using trafilatura."""
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None
        return trafilatura.extract(downloaded)
    except Exception:
        return None
