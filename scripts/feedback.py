"""Feedback loop: update corpus, wiki, and taste stats after daily scoring."""

from __future__ import annotations

import copy
import json
import logging
from collections import Counter
from datetime import date
from pathlib import Path

from scripts.config import load_taste_profile, save_taste_profile, get_wiki_path
from scripts.embedding_store import append_to_corpus
from scripts.taste_engine import ScoredPaper

logger = logging.getLogger(__name__)

_RELEVANCE_RANK = {"High": 2, "Medium": 1, "Low": 0}


# ---------------------------------------------------------------------------
# Corpus update
# ---------------------------------------------------------------------------


def update_corpus(
    scored: list[ScoredPaper],
    corpus_dir: Path,
    relevance_threshold: str = "High",
) -> int:
    """Add papers at or above threshold to the embedding corpus.

    Deduplicates against existing corpus by title. Returns count added.
    """
    min_level = _RELEVANCE_RANK.get(relevance_threshold, 2)

    to_add = [
        sp for sp in scored
        if _RELEVANCE_RANK.get(sp.relevance, 0) >= min_level
    ]
    if not to_add:
        logger.info("No papers above threshold to add to corpus")
        return 0

    # Deduplicate against existing corpus
    metadata_path = corpus_dir / "corpus_metadata.json"
    existing_titles: set[str] = set()
    if metadata_path.exists():
        existing_meta = json.loads(metadata_path.read_text(encoding="utf-8"))
        existing_titles = {m.get("title", "") for m in existing_meta}

    new_papers = [
        sp for sp in to_add
        if sp.paper.get("title", "") not in existing_titles
    ]
    if not new_papers:
        logger.info("All scored papers already in corpus")
        return 0

    texts = [
        f"{sp.paper.get('title', '')}. {sp.paper.get('abstract', '')}"
        for sp in new_papers
    ]
    metadata = [
        {
            "title": sp.paper.get("title", ""),
            "url": sp.paper.get("url", ""),
            "arxiv_id": sp.paper.get("arxiv_id", ""),
            "date": sp.paper.get("date", date.today().strftime("%Y.%m")),
            "authors": sp.paper.get("authors", []),
            "relevance": sp.relevance,
            "added_by": "feedback",
        }
        for sp in new_papers
    ]

    embeddings_path = corpus_dir / "corpus_embeddings.npy"
    append_to_corpus(texts, metadata, embeddings_path, metadata_path)
    logger.info("Added %d papers to corpus", len(new_papers))
    return len(new_papers)


# ---------------------------------------------------------------------------
# Taste profile stats
# ---------------------------------------------------------------------------


def update_taste_stats(
    scored: list[ScoredPaper],
    profile_path: Path | None = None,
) -> dict:
    """Update taste profile stats with today's scoring results.

    Keeps a rolling 90-day daily_history. Returns updated profile.
    """
    original = load_taste_profile(profile_path)
    updated = copy.deepcopy(original)

    stats = updated.setdefault("stats", {})
    relevance_counts = Counter(sp.relevance for sp in scored)

    history = stats.setdefault("daily_history", [])
    history.append({
        "date": date.today().isoformat(),
        "scored": len(scored),
        "high": relevance_counts.get("High", 0),
        "medium": relevance_counts.get("Medium", 0),
        "low": relevance_counts.get("Low", 0),
    })
    # Keep last 90 days
    history[:] = history[-90:]
    stats["last_updated"] = date.today().isoformat()

    save_taste_profile(updated, profile_path)
    logger.info(
        "Updated taste stats: %d scored (H=%d M=%d L=%d)",
        len(scored),
        relevance_counts.get("High", 0),
        relevance_counts.get("Medium", 0),
        relevance_counts.get("Low", 0),
    )
    return updated


# ---------------------------------------------------------------------------
# Wiki compilation
# ---------------------------------------------------------------------------


def compile_wiki_for_scored(
    scored: list[ScoredPaper],
    wiki_dir: Path | None = None,
    relevance_threshold: str = "High",
) -> int:
    """Compile wiki pages for papers at or above threshold.

    Uses the v2 two-step compiler: ingest raw data, then compile paper + concepts
    in two LLM calls. Falls back to v1 if raw ingest fails.
    Returns count compiled.
    """
    from scripts.raw_ingest import ingest_paper
    from scripts.wiki_compiler import compile_paper_v2, build_index_pages

    resolved_wiki_dir = wiki_dir if wiki_dir is not None else get_wiki_path()
    min_level = _RELEVANCE_RANK.get(relevance_threshold, 2)

    to_compile = [
        sp for sp in scored
        if _RELEVANCE_RANK.get(sp.relevance, 0) >= min_level
    ]
    if not to_compile:
        return 0

    compiled = 0
    for sp in to_compile:
        paper = sp.paper
        arxiv_id = paper.get("arxiv_id", "")
        title = paper.get("title", "unknown")

        if not arxiv_id:
            logger.warning("Skipping paper without arxiv_id: %s", title)
            continue

        # 1. Ingest raw data
        try:
            ingest_paper(arxiv_id, resolved_wiki_dir)
        except Exception:
            logger.exception("Failed to ingest raw data for %s, skipping", arxiv_id)
            continue

        # 2. Compile paper + concepts via v2 two-step compiler
        try:
            compile_paper_v2(arxiv_id, wiki_dir=resolved_wiki_dir)
            compiled += 1
        except Exception:
            logger.exception("Failed to compile paper v2: %s (%s)", title, arxiv_id)

    # Rebuild index pages
    try:
        build_index_pages(resolved_wiki_dir)
    except Exception:
        logger.exception("Failed to rebuild wiki index pages")

    logger.info("Wiki compiled for %d papers", compiled)
    return compiled


# ---------------------------------------------------------------------------
# Main entry point (called by daily_pipeline)
# ---------------------------------------------------------------------------


def run_feedback(
    scored: list[ScoredPaper],
    corpus_dir: Path,
    wiki_dir: Path | None = None,
    profile_path: Path | None = None,
    compile_wiki: bool = True,
) -> dict:
    """Run the full feedback loop after daily scoring.

    1. Add high-scored papers to corpus (L2 improves over time)
    2. Update taste profile statistics
    3. Compile wiki pages for high-scored papers
    """
    result = {
        "papers_added_to_corpus": 0,
        "wiki_compiled": 0,
        "stats_updated": False,
    }

    # Step 1: Corpus update
    try:
        result["papers_added_to_corpus"] = update_corpus(scored, corpus_dir)
    except Exception:
        logger.exception("Corpus update failed")

    # Step 2: Taste stats
    try:
        update_taste_stats(scored, profile_path)
        result["stats_updated"] = True
    except Exception:
        logger.exception("Taste stats update failed")

    # Step 3: Wiki compilation (expensive — calls Claude for each paper)
    if compile_wiki:
        try:
            result["wiki_compiled"] = compile_wiki_for_scored(
                scored, wiki_dir
            )
        except Exception:
            logger.exception("Wiki compilation failed")

    return result
