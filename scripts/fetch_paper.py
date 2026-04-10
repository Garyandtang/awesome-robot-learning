"""Fetch paper metadata and full text from arXiv and Semantic Scholar APIs."""

import io
import logging
import re
import time

import feedparser
import requests
import trafilatura

logger = logging.getLogger(__name__)

ARXIV_API = "http://export.arxiv.org/api/query"
S2_API = "https://api.semanticscholar.org/graph/v1/paper"

# arXiv throttles clients using the default `python-requests/...` User-Agent
# quite aggressively, so always identify ourselves with a real UA string.
_USER_AGENT = "paper-collector/1.0 (research tool; +https://github.com/)"

ARXIV_ID_RE = re.compile(r"(\d{4}\.\d{4,5})")


def parse_arxiv_id(url_or_id: str) -> str | None:
    """Extract arXiv ID from a URL or bare ID string."""
    match = ARXIV_ID_RE.search(url_or_id)
    return match.group(1) if match else None


def fetch_arxiv_metadata(arxiv_id: str) -> dict | None:
    """Fetch metadata for a single paper from arXiv Atom API.

    Sends an explicit User-Agent (arXiv throttles default `python-requests`
    much harder) and retries with exponential backoff on HTTP 429.
    """
    headers = {"User-Agent": _USER_AGENT}
    max_retries = 5
    backoff = 5  # 5, 10, 20, 40, 80 seconds
    resp = None
    for attempt in range(max_retries):
        resp = requests.get(
            ARXIV_API,
            params={"id_list": arxiv_id, "max_results": 1},
            headers=headers,
            timeout=30,
        )
        if resp.status_code == 429 and attempt < max_retries - 1:
            logger.warning(
                "arXiv 429 for %s (attempt %d/%d); sleeping %ds",
                arxiv_id,
                attempt + 1,
                max_retries,
                backoff,
            )
            time.sleep(backoff)
            backoff *= 2
            continue
        break
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


# ---------------------------------------------------------------------------
# Full text fetching (HTML preferred, PDF fallback)
# ---------------------------------------------------------------------------

_MAX_FULLTEXT_CHARS = 80_000  # ~20K tokens, enough for Claude analysis


def fetch_fulltext_html(arxiv_id: str, timeout: int = 30) -> str | None:
    """Fetch full text from arXiv HTML rendering.

    Returns extracted text or None if HTML version unavailable.
    """
    url = f"https://arxiv.org/html/{arxiv_id}v1"
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None
        text = trafilatura.extract(downloaded, include_tables=False)
        if text and len(text) > 500:  # sanity check: real paper > 500 chars
            return text[:_MAX_FULLTEXT_CHARS]
        return None
    except Exception:
        logger.debug("HTML fetch failed for %s", arxiv_id)
        return None


def fetch_fulltext_pdf(arxiv_id: str, timeout: int = 60) -> str | None:
    """Fetch full text by downloading arXiv PDF and extracting with pymupdf.

    Returns extracted text or None on failure.
    """
    try:
        import pymupdf
    except ImportError:
        logger.debug("pymupdf not installed, skipping PDF fallback")
        return None

    url = f"https://arxiv.org/pdf/{arxiv_id}"
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
    except Exception:
        logger.debug("PDF download failed for %s", arxiv_id)
        return None

    try:
        doc = pymupdf.open(stream=io.BytesIO(resp.content), filetype="pdf")
        pages = []
        for page in doc:
            pages.append(page.get_text())
        doc.close()
        text = "\n".join(pages)
        if len(text) > 500:
            return text[:_MAX_FULLTEXT_CHARS]
        return None
    except Exception:
        logger.debug("PDF parsing failed for %s", arxiv_id)
        return None


def fetch_fulltext(arxiv_id: str) -> str | None:
    """Fetch paper full text: try HTML first, fall back to PDF.

    Returns plain text content (truncated to ~80K chars) or None.
    """
    if not arxiv_id:
        return None

    # Strategy B: HTML first (fast, clean)
    text = fetch_fulltext_html(arxiv_id)
    if text:
        logger.info("Got HTML full text for %s (%d chars)", arxiv_id, len(text))
        return text

    # Strategy A fallback: PDF (slower, noisier)
    text = fetch_fulltext_pdf(arxiv_id)
    if text:
        logger.info("Got PDF full text for %s (%d chars)", arxiv_id, len(text))
        return text

    logger.info("No full text available for %s", arxiv_id)
    return None


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
