"""Monthly source discovery: find new RSS/blog sources from prolific authors."""

from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def extract_top_authors_from_corpus(
    corpus_metadata: list[dict],
    min_papers: int = 3,
) -> list[dict]:
    """Extract most frequent authors from the embedding corpus metadata.

    Count author appearances across all papers. Return authors with >= min_papers.
    Returns: list of {name, paper_count} sorted by count descending.
    """
    author_counter: Counter[str] = Counter()
    for entry in corpus_metadata:
        for author in entry.get("authors", []):
            author_counter[author] += 1

    return [
        {"name": name, "paper_count": count}
        for name, count in author_counter.most_common()
        if count >= min_papers
    ]


def search_author_pages(
    authors: list[dict],
    api_key: str = "",
) -> list[dict]:
    """Search for author homepages via Semantic Scholar API.

    For each author, search S2 for their profile. Extract homepage URL and
    affiliation.

    Returns: list of {name, homepage_url, affiliation, paper_count}.

    Note: This is a placeholder implementation. A future version will query the
    Semantic Scholar API using *api_key* to resolve real homepage URLs and
    affiliations.
    """
    results: list[dict] = []
    for author in authors:
        results.append(
            {
                "name": author["name"],
                "homepage_url": "",
                "affiliation": "",
                "paper_count": author.get("paper_count", 0),
            }
        )
    return results


def generate_feed_candidates(
    authors: list[dict],
    existing_feeds: list[dict],
) -> list[dict]:
    """Generate RSS feed candidates from author/lab pages.

    Deduplicates against existing feeds by comparing URL domains.
    Returns: list of candidate feed dicts for feeds.yaml.
    """
    existing_domains: set[str] = set()
    for feed in existing_feeds:
        url = feed.get("url", "")
        if url:
            existing_domains.add(urlparse(url).netloc.lower())

    candidates: list[dict] = []
    for author in authors:
        homepage = author.get("homepage_url", "")
        if not homepage:
            continue

        domain = urlparse(homepage).netloc.lower()
        if domain in existing_domains:
            continue

        candidates.append(
            {
                "name": author["name"],
                "url": homepage,
                "type": "author_homepage",
                "paper_count": author.get("paper_count", 0),
            }
        )

    logger.info(
        "Feed candidates: %d authors -> %d new candidates (after dedup against %d existing feeds)",
        len(authors),
        len(candidates),
        len(existing_feeds),
    )
    return candidates


def run_monthly_discovery(
    corpus_dir: Path,
    feeds_path: Path,
    output_path: Path,
) -> dict:
    """Run the monthly source discovery pipeline.

    Returns: {authors_analyzed, candidates_found}
    """
    corpus_dir = Path(corpus_dir)
    feeds_path = Path(feeds_path)
    output_path = Path(output_path)

    # Load corpus metadata
    metadata_path = corpus_dir / "metadata.json"
    if metadata_path.exists():
        corpus_metadata: list[dict] = json.loads(metadata_path.read_text())
    else:
        logger.warning("No corpus metadata found at %s", metadata_path)
        corpus_metadata = []

    # Step 1: Extract top authors
    top_authors = extract_top_authors_from_corpus(corpus_metadata, min_papers=3)
    logger.info("Found %d prolific authors", len(top_authors))

    # Step 2: Search for author pages (placeholder for now)
    authors_with_pages = search_author_pages(top_authors)

    # Step 3: Load existing feeds
    existing_feeds: list[dict] = []
    if feeds_path.exists():
        import yaml  # optional dependency, only needed for pipeline entry point

        existing_feeds = yaml.safe_load(feeds_path.read_text()) or []

    # Step 4: Generate candidates
    candidates = generate_feed_candidates(authors_with_pages, existing_feeds)

    # Step 5: Write candidates to output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(candidates, indent=2, ensure_ascii=False))
    logger.info("Wrote %d candidates to %s", len(candidates), output_path)

    return {
        "authors_analyzed": len(top_authors),
        "candidates_found": len(candidates),
    }
