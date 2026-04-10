"""Search for real Force-VLA papers and output verified arXiv IDs.

Usage:
    python3 -m scripts.search_force_vla
"""

from __future__ import annotations

import logging
import time

import feedparser
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ARXIV_API = "http://export.arxiv.org/api/query"
S2_API = "https://api.semanticscholar.org/graph/v1/paper/search"

# Force-VLA search queries — broad enough to catch relevant papers
ARXIV_QUERIES = [
    # Force/torque + robot manipulation + learning
    '(cat:cs.RO) AND (ti:"force" OR ti:"torque") AND (ti:"manipulation" OR ti:"policy" OR ti:"learning")',
    # Tactile + robot + VLA/policy
    '(cat:cs.RO) AND (ti:"tactile") AND (ti:"manipulation" OR ti:"policy" OR ti:"VLA")',
    # Impedance/compliance + learning/control
    '(cat:cs.RO) AND (ti:"impedance" OR ti:"compliance") AND (ti:"learning" OR ti:"adaptive")',
    # Contact-rich + manipulation
    '(cat:cs.RO) AND (ti:"contact") AND (ti:"manipulation" OR ti:"policy")',
    # Force-aware / force-guided
    '(cat:cs.RO) AND (ti:"force-aware" OR ti:"force-guided" OR ti:"force-centric")',
]

S2_QUERIES = [
    "force-aware robot manipulation policy learning",
    "tactile vision fusion robot manipulation",
    "variable impedance control learning manipulation",
    "contact-rich manipulation policy diffusion",
    "force torque sensing robot learning",
    "VLA force tactile manipulation",
]


def search_arxiv_no_date_filter(query: str, max_results: int = 50) -> list[dict]:
    """Search arXiv without date filtering."""
    resp = requests.get(
        ARXIV_API,
        params={
            "search_query": query,
            "sortBy": "relevance",
            "sortOrder": "descending",
            "max_results": max_results,
        },
        timeout=60,
    )
    resp.raise_for_status()
    feed = feedparser.parse(resp.text)
    papers = []
    for entry in feed.entries:
        arxiv_id = entry.id.split("/abs/")[-1].split("v")[0] if "/abs/" in entry.id else ""
        if not arxiv_id:
            continue
        published = entry.get("published", "")
        parts = published.split("-") if published else []
        date_str = f"{parts[0]}.{parts[1]}" if len(parts) >= 2 else ""
        papers.append({
            "arxiv_id": arxiv_id,
            "title": entry.title.replace("\n", " ").strip(),
            "date": date_str,
            "abstract": (entry.summary or "").replace("\n", " ").strip()[:200],
        })
    return papers


def search_s2(query: str, max_results: int = 30) -> list[dict]:
    """Search Semantic Scholar for papers with arXiv IDs."""
    params = {
        "query": query,
        "limit": min(max_results, 100),
        "fields": "title,externalIds,year,abstract",
        "fieldsOfStudy": "Computer Science",
    }
    try:
        resp = requests.get(S2_API, params=params, timeout=30)
        if resp.status_code == 429:
            time.sleep(5)
            resp = requests.get(S2_API, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("S2 search failed for '%s': %s", query, e)
        return []

    papers = []
    for item in data.get("data", []):
        ext_ids = item.get("externalIds") or {}
        arxiv_id = ext_ids.get("ArXiv", "")
        if not arxiv_id:
            continue
        papers.append({
            "arxiv_id": arxiv_id,
            "title": (item.get("title") or "").strip(),
            "date": str(item.get("year") or ""),
            "abstract": ((item.get("abstract") or "")[:200]).strip(),
        })
    return papers


def deduplicate(papers: list[dict]) -> list[dict]:
    """Deduplicate by arXiv ID."""
    seen = {}
    for p in papers:
        aid = p["arxiv_id"]
        if aid and aid not in seen:
            seen[aid] = p
    return list(seen.values())


def is_force_vla_relevant(paper: dict) -> bool:
    """Quick relevance filter based on title keywords."""
    title = paper["title"].lower()
    abstract = paper.get("abstract", "").lower()
    text = title + " " + abstract

    # Must mention robot/manipulation/grasping/dexterous
    robot_terms = ["robot", "manipulat", "grasp", "dexterous", "hand", "assembly", "insertion"]
    if not any(t in text for t in robot_terms):
        return False

    # Must mention force/tactile/impedance/contact/compliance
    force_terms = ["force", "tactile", "torque", "impedance", "compliance", "contact-rich",
                   "haptic", "stiffness", "wrench"]
    if not any(t in text for t in force_terms):
        return False

    return True


def main() -> None:
    all_papers: list[dict] = []

    # arXiv searches
    for i, query in enumerate(ARXIV_QUERIES):
        logger.info("arXiv search %d/%d: %s", i + 1, len(ARXIV_QUERIES), query[:80])
        try:
            papers = search_arxiv_no_date_filter(query, max_results=40)
            all_papers.extend(papers)
            logger.info("  Found %d papers", len(papers))
        except Exception as e:
            logger.warning("  arXiv search failed: %s", e)
        time.sleep(3)  # Rate limit

    # S2 searches
    for i, query in enumerate(S2_QUERIES):
        logger.info("S2 search %d/%d: %s", i + 1, len(S2_QUERIES), query)
        papers = search_s2(query, max_results=30)
        all_papers.extend(papers)
        logger.info("  Found %d papers", len(papers))
        time.sleep(1)

    # Deduplicate
    unique = deduplicate(all_papers)
    logger.info("Total unique papers: %d", len(unique))

    # Filter for relevance
    relevant = [p for p in unique if is_force_vla_relevant(p)]
    logger.info("Relevant Force-VLA papers: %d", len(relevant))

    # Sort by date descending
    relevant.sort(key=lambda p: p.get("date", ""), reverse=True)

    # Output as Python list for cold_start script
    print("\n" + "=" * 80)
    print("VERIFIED FORCE-VLA PAPERS")
    print("=" * 80)
    print(f"# {len(relevant)} papers found\n")
    print("FORCE_VLA_PAPERS = [")
    for p in relevant:
        print(f'    {{"id": "{p["arxiv_id"]}", "title": "{p["title"][:80]}"}},')
    print("]")


if __name__ == "__main__":
    main()
