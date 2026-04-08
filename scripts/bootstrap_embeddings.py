"""Bootstrap embedding corpus from cold-start paper list."""

import logging
import time
from pathlib import Path

from scripts.embedding_store import bootstrap_corpus, load_corpus
from scripts.fetch_paper import fetch_arxiv_metadata
from scripts.profile_bootstrap import parse_awesome_list_entries

logger = logging.getLogger(__name__)


def enrich_with_abstracts(
    papers: list[dict],
    batch_size: int = 10,
    delay: float = 3.0,
) -> list[dict]:
    """Fetch abstracts from arXiv for papers that have arxiv_ids.

    Rate-limited to avoid API throttling. Returns new list (immutable).
    For papers without arxiv_id or where fetch fails, keep them with empty abstract.
    """
    enriched: list[dict] = []

    for batch_start in range(0, len(papers), batch_size):
        batch = papers[batch_start : batch_start + batch_size]

        for paper in batch:
            arxiv_id = paper.get("arxiv_id")
            if not arxiv_id:
                enriched.append({**paper})
                continue

            try:
                metadata = fetch_arxiv_metadata(arxiv_id)
                abstract = (metadata or {}).get("abstract", "")
                enriched.append({**paper, "abstract": abstract})
            except Exception:
                logger.warning(
                    "Failed to fetch abstract for %s, skipping",
                    arxiv_id,
                    exc_info=True,
                )
                enriched.append({**paper})

        # Rate-limit between batches (skip delay after the last batch)
        if delay > 0 and batch_start + batch_size < len(papers):
            logger.debug("Sleeping %.1fs between batches", delay)
            time.sleep(delay)

    logger.info(
        "Enriched %d/%d papers with abstracts",
        sum(1 for p in enriched if p.get("abstract")),
        len(enriched),
    )
    return enriched


def run_bootstrap(
    readme_path: Path,
    corpus_dir: Path,
    fetch_abstracts: bool = True,
) -> dict:
    """Run the full bootstrap pipeline.

    1. Read README.md
    2. Parse entries via parse_awesome_list_entries()
    3. Optionally enrich with abstracts
    4. Call bootstrap_corpus()
    5. Returns: {total_papers, papers_with_abstracts, corpus_size}
    """
    # Resume check: if corpus already exists with same count, skip
    existing_embeddings, existing_metadata = load_corpus(corpus_dir)
    text = readme_path.read_text(encoding="utf-8")
    papers = parse_awesome_list_entries(text)

    if existing_embeddings is not None and len(existing_metadata) == len(papers):
        logger.info(
            "Corpus already exists with %d papers, skipping bootstrap",
            len(existing_metadata),
        )
        return {
            "total_papers": len(papers),
            "papers_with_abstracts": sum(
                1 for p in existing_metadata if p.get("abstract")
            ),
            "corpus_size": len(existing_metadata),
        }

    if fetch_abstracts:
        papers = enrich_with_abstracts(papers)

    embeddings, metadata = bootstrap_corpus(papers, corpus_dir)

    papers_with_abstracts = sum(1 for p in metadata if p.get("abstract"))
    corpus_size = embeddings.shape[0]

    logger.info(
        "Bootstrap complete: %d papers, %d with abstracts, corpus size %d",
        len(papers),
        papers_with_abstracts,
        corpus_size,
    )

    return {
        "total_papers": len(papers),
        "papers_with_abstracts": papers_with_abstracts,
        "corpus_size": corpus_size,
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    humanoid_readme = Path(
        "/home/gary/Documents/awesome-humanoid-robot-learning/README.md"
    )
    repo_root = Path(__file__).resolve().parent.parent
    corpus_dir = repo_root / "data" / "embeddings"

    result = run_bootstrap(humanoid_readme, corpus_dir, fetch_abstracts=True)
    print(f"Total papers: {result['total_papers']}")
    print(f"Papers with abstracts: {result['papers_with_abstracts']}")
    print(f"Corpus size: {result['corpus_size']}")
