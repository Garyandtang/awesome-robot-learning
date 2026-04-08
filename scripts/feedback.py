"""Feedback loop: when a paper is collected, update all systems."""

import copy
import logging
from datetime import date
from pathlib import Path

from scripts.config import load_taste_profile, save_taste_profile, get_wiki_path
from scripts.embedding_store import append_to_corpus

logger = logging.getLogger(__name__)


def update_taste_stats(paper: dict, profile_path: Path | None = None) -> dict:
    """Update taste_profile stats with a newly collected paper.

    Immutable: loads profile, creates updated copy, saves it.
    Returns the updated profile.
    """
    original = load_taste_profile(profile_path)
    updated = copy.deepcopy(original)

    stats = updated.setdefault("stats", {})
    stats["total_collected"] = stats.get("total_collected", 0) + 1
    stats["last_updated"] = date.today().isoformat()

    category = paper.get("category", "")
    if category:
        top_categories = stats.setdefault("top_categories", [])
        matched = [c for c in top_categories if c.get("category") == category]
        if matched:
            matched[0]["count"] = matched[0].get("count", 0) + 1
        else:
            top_categories.append({"category": category, "count": 1})

    save_taste_profile(updated, profile_path)
    return updated


def add_paper_to_corpus(paper: dict, corpus_dir: Path) -> None:
    """Generate embedding text and append to corpus."""
    text = f"{paper.get('title', '')}. {paper.get('abstract', '')}"
    append_to_corpus(
        new_texts=[text],
        new_metadata=[paper],
        embeddings_path=corpus_dir / "corpus_embeddings.npy",
        metadata_path=corpus_dir / "corpus_metadata.json",
    )


def on_collect_paper(
    paper: dict,
    corpus_dir: Path,
    taste_profile_path: Path | None = None,
    wiki_dir: Path | None = None,
    compile_wiki: bool = True,
) -> dict:
    """Handle a paper being collected/approved by the user.

    Steps:
    1. Update taste_profile.yaml (increment stats.total_collected, add category count)
    2. Generate embedding and append to corpus
    3. If compile_wiki=True, trigger wiki compilation for this paper

    Returns: {profile_updated: bool, embedding_added: bool, wiki_compiled: bool}
    """
    result = {
        "profile_updated": False,
        "embedding_added": False,
        "wiki_compiled": False,
    }

    # Step 1: Update taste profile
    try:
        update_taste_stats(paper, taste_profile_path)
        result["profile_updated"] = True
    except Exception:
        logger.exception("Failed to update taste stats for: %s", paper.get("title", ""))

    # Step 2: Add paper embedding to corpus
    try:
        add_paper_to_corpus(paper, corpus_dir)
        result["embedding_added"] = True
    except Exception:
        logger.exception("Failed to add paper to corpus: %s", paper.get("title", ""))

    # Step 3: Compile wiki pages if requested
    if compile_wiki:
        try:
            from scripts.wiki_compiler import (
                compile_paper_page,
                extract_concepts_llm,
                create_concept_page,
                update_concept_page,
                get_concept_index,
                _slugify,
            )

            resolved_wiki_dir = wiki_dir if wiki_dir is not None else get_wiki_path()

            compile_paper_page(paper, resolved_wiki_dir)

            concepts = extract_concepts_llm(paper, resolved_wiki_dir)
            existing_concepts = get_concept_index(resolved_wiki_dir)
            existing_slugs = {_slugify(c) for c in existing_concepts}

            for concept in concepts:
                try:
                    slug = _slugify(concept)
                    concept_path = resolved_wiki_dir / "concepts" / f"{slug}.md"
                    if concept_path.exists():
                        update_concept_page(concept, paper, resolved_wiki_dir)
                    else:
                        create_concept_page(concept, paper, resolved_wiki_dir)
                except Exception:
                    logger.exception(
                        "Failed to create/update concept '%s' for paper: %s",
                        concept,
                        paper.get("title", ""),
                    )

            result["wiki_compiled"] = True
        except Exception:
            logger.exception("Failed to compile wiki for: %s", paper.get("title", ""))

    return result
