"""Search arXiv and Semantic Scholar for new papers."""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import feedparser
import requests

ARXIV_API = "http://export.arxiv.org/api/query"
S2_API = "https://api.semanticscholar.org/graph/v1/paper/search"


def build_arxiv_query(
    categories: list[str],
    keywords: list[str] | None = None,
) -> str:
    """Build an arXiv API search query string."""
    cat_query = " OR ".join(f"cat:{c}" for c in categories)
    if not keywords:
        return f"({cat_query})"
    kw_query = " OR ".join(f'ti:"{kw}"' for kw in keywords)
    return f"({cat_query}) AND ({kw_query})"


def build_s2_query(keywords: list[str]) -> str:
    """Build a Semantic Scholar search query string."""
    return " ".join(keywords)


def search_arxiv(
    query: str,
    max_results: int = 100,
    days_back: int = 1,
) -> list[dict]:
    """Search arXiv and return list of paper metadata dicts."""
    resp = requests.get(
        ARXIV_API,
        params={
            "search_query": query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": max_results,
        },
        timeout=60,
    )
    resp.raise_for_status()
    feed = feedparser.parse(resp.text)
    cutoff = datetime.utcnow() - timedelta(days=days_back)
    papers = []
    for entry in feed.entries:
        published = entry.get("published", "")
        if not published:
            continue
        try:
            pub_dt = datetime.strptime(published[:10], "%Y-%m-%d")
        except ValueError:
            continue
        if pub_dt < cutoff:
            continue
        # Extract arXiv ID from entry.id URL
        arxiv_id = entry.id.split("/abs/")[-1].split("v")[0] if "/abs/" in entry.id else ""
        if not arxiv_id:
            continue
        parts = published.split("-")
        date_str = f"{parts[0]}.{parts[1]}" if len(parts) >= 2 else ""
        papers.append({
            "title": entry.title.replace("\n", " ").strip(),
            "authors": [a.get("name", "") for a in entry.get("authors", [])],
            "abstract": entry.summary.replace("\n", " ").strip() if entry.get("summary") else "",
            "url": f"https://arxiv.org/abs/{arxiv_id}",
            "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
            "venue": "arXiv",
            "date": date_str,
            "arxiv_id": arxiv_id,
            "project_url": None,
            "has_code": False,
        })
    return papers


def search_semantic_scholar(
    query: str,
    fields_of_study: list[str] | None = None,
    max_results: int = 50,
    year: str | None = None,
    api_key: str = "",
) -> list[dict]:
    """Search Semantic Scholar and return list of paper metadata dicts."""
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key
    params = {
        "query": query,
        "limit": min(max_results, 100),
        "fields": "title,authors,abstract,externalIds,year,venue,isOpenAccess,openAccessPdf",
    }
    if fields_of_study:
        params["fieldsOfStudy"] = ",".join(fields_of_study)
    if year:
        params["year"] = year
    resp = requests.get(S2_API, params=params, headers=headers, timeout=30)
    if resp.status_code == 429:
        time.sleep(5)
        resp = requests.get(S2_API, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    papers = []
    for item in data.get("data", []):
        ext_ids = item.get("externalIds") or {}
        arxiv_id = ext_ids.get("ArXiv", "")
        year_val = item.get("year") or ""
        oa_pdf = item.get("openAccessPdf") or {}
        papers.append({
            "title": (item.get("title") or "").strip(),
            "authors": [a["name"] for a in (item.get("authors") or []) if "name" in a],
            "abstract": (item.get("abstract") or "").strip(),
            "url": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "",
            "pdf_url": oa_pdf.get("url", ""),
            "venue": item.get("venue") or "arXiv",
            "date": str(year_val),
            "arxiv_id": arxiv_id,
            "project_url": None,
            "has_code": item.get("isOpenAccess", False),
        })
    return papers


def deduplicate(papers: list[dict], seen: dict) -> list[dict]:
    """Remove duplicates and already-seen papers."""
    unique = {}
    for p in papers:
        pid = p.get("arxiv_id") or p.get("title", "")
        if pid and pid not in seen and pid not in unique:
            unique[pid] = p
    return list(unique.values())


def load_seen(path: Path) -> dict:
    """Load seen papers record."""
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_seen(path: Path, seen: dict) -> None:
    """Save seen papers record."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2, ensure_ascii=False)
