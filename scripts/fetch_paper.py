"""Fetch paper metadata from arXiv and Semantic Scholar APIs."""

import re
import time

import feedparser
import requests

ARXIV_API = "http://export.arxiv.org/api/query"
S2_API = "https://api.semanticscholar.org/graph/v1/paper"

ARXIV_ID_RE = re.compile(r"(\d{4}\.\d{4,5})")


def parse_arxiv_id(url_or_id: str) -> str | None:
    """Extract arXiv ID from a URL or bare ID string."""
    match = ARXIV_ID_RE.search(url_or_id)
    return match.group(1) if match else None


def fetch_arxiv_metadata(arxiv_id: str) -> dict | None:
    """Fetch metadata for a single paper from arXiv Atom API."""
    resp = requests.get(
        ARXIV_API,
        params={"id_list": arxiv_id, "max_results": 1},
        timeout=30,
    )
    resp.raise_for_status()
    feed = feedparser.parse(resp.text)
    if not feed.entries:
        return None
    entry = feed.entries[0]
    # arXiv returns a default entry for invalid IDs; check for actual content
    if "title" not in entry or entry.title == "Error":
        return None
    published = entry.get("published", "")
    date_str = ""
    if published:
        # published format: "2017-06-12T17:57:34Z"
        parts = published.split("-")
        if len(parts) >= 2:
            date_str = f"{parts[0]}.{parts[1]}"
    return {
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
    }


def fetch_s2_metadata(
    arxiv_id: str | None = None,
    s2_id: str | None = None,
    api_key: str = "",
) -> dict | None:
    """Fetch metadata from Semantic Scholar Academic Graph API."""
    if arxiv_id:
        paper_id = f"ARXIV:{arxiv_id}"
    elif s2_id:
        paper_id = s2_id
    else:
        return None
    headers = {"User-Agent": "paper-collector/1.0 (research tool)"}
    if api_key:
        headers["x-api-key"] = api_key
    fields = "title,authors,abstract,externalIds,url,year,venue,isOpenAccess,openAccessPdf"
    max_retries = 4
    for attempt in range(max_retries):
        resp = requests.get(
            f"{S2_API}/{paper_id}",
            params={"fields": fields},
            headers=headers,
            timeout=30,
        )
        if resp.status_code == 429 and attempt < max_retries - 1:
            time.sleep(5 * (attempt + 1))
            continue
        break
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json()
    ext_ids = data.get("externalIds") or {}
    resolved_arxiv_id = ext_ids.get("ArXiv", arxiv_id)
    year = data.get("year") or ""
    date_str = f"{year}" if year else ""
    oa_pdf = data.get("openAccessPdf") or {}
    return {
        "title": (data.get("title") or "").strip(),
        "authors": [a["name"] for a in (data.get("authors") or []) if "name" in a],
        "abstract": (data.get("abstract") or "").strip(),
        "url": f"https://arxiv.org/abs/{resolved_arxiv_id}" if resolved_arxiv_id else (data.get("url") or ""),
        "pdf_url": oa_pdf.get("url", f"https://arxiv.org/pdf/{resolved_arxiv_id}" if resolved_arxiv_id else ""),
        "venue": data.get("venue") or "arXiv",
        "date": date_str,
        "arxiv_id": resolved_arxiv_id or "",
        "project_url": None,
        "has_code": data.get("isOpenAccess", False),
    }


def fetch_paper(url_or_id: str, api_key: str = "") -> dict | None:
    """Fetch paper metadata, trying arXiv first, then enriching with S2."""
    arxiv_id = parse_arxiv_id(url_or_id)
    if arxiv_id:
        meta = fetch_arxiv_metadata(arxiv_id)
        if meta:
            # Try to enrich with S2 data (citation count, open access info)
            s2 = fetch_s2_metadata(arxiv_id=arxiv_id, api_key=api_key)
            if s2 and s2.get("has_code"):
                meta["has_code"] = True
            return meta
    # Fallback: try as Semantic Scholar ID
    s2 = fetch_s2_metadata(s2_id=url_or_id, api_key=api_key)
    return s2
