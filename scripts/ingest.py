"""Manual paper ingest CLI: fetch raw data + compile to wiki.

Usage:
    python3 -m scripts.ingest 2411.15753
    python3 -m scripts.ingest 2411.15753 2503.08548
    python3 -m scripts.ingest --ingest-only 2411.15753
    python3 -m scripts.ingest --compile-only 2411.15753
    python3 -m scripts.ingest --force 2411.15753
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from scripts.config import get_wiki_path
from scripts.index_builder import build_all_indexes
from scripts.raw_ingest import ingest_paper
from scripts.wiki_compiler import compile_paper_v2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def ingest_and_compile(
    arxiv_ids: list[str],
    wiki_dir: Path | None = None,
    *,
    ingest_only: bool = False,
    compile_only: bool = False,
    force: bool = False,
) -> dict:
    """Ingest and compile papers into the wiki.

    Steps:
    1. ingest_paper() for each ID (skip with compile_only)
    2. compile_paper_v2() for each ID (skip with ingest_only)
    3. build_all_indexes() to rebuild wiki indexes

    Returns {"ingested": int, "compiled": int, "failed": list[str]}.
    """
    resolved = wiki_dir if wiki_dir is not None else get_wiki_path()
    result = {"ingested": 0, "compiled": 0, "failed": []}

    for arxiv_id in arxiv_ids:
        # Step 1: Ingest raw data
        if not compile_only:
            try:
                ingest_paper(arxiv_id, resolved, force=force)
                result["ingested"] += 1
                logger.info("Ingested %s", arxiv_id)
            except Exception:
                logger.exception("Failed to ingest %s", arxiv_id)
                result["failed"].append(arxiv_id)
                continue

        # Step 2: Compile to wiki
        if not ingest_only:
            meta_path = resolved / "raw" / "papers" / arxiv_id / "meta.yaml"
            if not meta_path.exists():
                logger.warning("No raw data for %s, skipping compilation", arxiv_id)
                result["failed"].append(arxiv_id)
                continue
            try:
                compile_paper_v2(arxiv_id, wiki_dir=resolved)
                result["compiled"] += 1
                logger.info("Compiled %s", arxiv_id)
            except Exception:
                logger.exception("Failed to compile %s", arxiv_id)
                result["failed"].append(arxiv_id)

    # Step 3: Rebuild indexes
    if not ingest_only and result["compiled"] > 0:
        build_all_indexes(resolved)
        logger.info("Indexes rebuilt")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest and compile papers into the wiki",
        usage="python3 -m scripts.ingest [OPTIONS] ARXIV_ID [ARXIV_ID ...]",
    )
    parser.add_argument("arxiv_ids", nargs="+", help="One or more arXiv IDs")
    parser.add_argument("--ingest-only", action="store_true", help="Only fetch raw data, skip compilation")
    parser.add_argument("--compile-only", action="store_true", help="Only compile (assumes raw data exists)")
    parser.add_argument("--force", action="store_true", help="Force re-ingest even if raw data exists")
    args = parser.parse_args()

    if args.ingest_only and args.compile_only:
        print("Error: --ingest-only and --compile-only are mutually exclusive", file=sys.stderr)
        sys.exit(1)

    result = ingest_and_compile(
        args.arxiv_ids,
        ingest_only=args.ingest_only,
        compile_only=args.compile_only,
        force=args.force,
    )

    summary = f"Done: {result['ingested']} ingested, {result['compiled']} compiled"
    if result["failed"]:
        summary += f", {len(result['failed'])} failed: {result['failed']}"
    logger.info(summary)


if __name__ == "__main__":
    main()
