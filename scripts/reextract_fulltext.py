"""Re-extract fulltext.md for all raw papers using Marker.

Iterates over every paper under ``wiki/raw/papers/*/`` and re-runs the
Marker-based fulltext extractor, overwriting each ``fulltext.md`` with
inline-LaTeX markdown. Skips metadata and image extraction.

Usage:

    python3 -m scripts.reextract_fulltext                 # all papers
    python3 -m scripts.reextract_fulltext 2411.15753      # one paper
    python3 -m scripts.reextract_fulltext --limit 5       # first 5
    python3 -m scripts.reextract_fulltext --dry-run       # list only
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from scripts.config import get_wiki_path
from scripts.raw_ingest import (
    RAW_PAPERS_DIR,
    _get_marker_converter,
    reextract_fulltext,
)

logger = logging.getLogger(__name__)


def discover_papers(wiki_dir: Path) -> list[str]:
    """Return sorted list of arxiv_ids under ``wiki/raw/papers/``."""
    papers_root = wiki_dir / RAW_PAPERS_DIR
    if not papers_root.exists():
        return []
    return sorted(
        p.name for p in papers_root.iterdir()
        if p.is_dir() and (p / "meta.yaml").exists()
    )


def run(
    arxiv_ids: list[str] | None = None,
    *,
    wiki_dir: Path | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict:
    """Batch re-extract fulltext for the given (or all) papers.

    Returns a summary dict with per-paper status.
    """
    resolved = wiki_dir if wiki_dir is not None else get_wiki_path()
    ids = arxiv_ids or discover_papers(resolved)
    if limit is not None:
        ids = ids[:limit]

    logger.info("Found %d paper(s) to re-extract", len(ids))
    if dry_run:
        for i, aid in enumerate(ids, 1):
            logger.info("[%d/%d] Would re-extract %s", i, len(ids), aid)
        return {"total": len(ids), "ok": 0, "failed": [], "skipped": [], "total_formulas": 0}

    # Pre-warm the Marker converter once so the first paper doesn't pay both
    # model load + conversion latency.
    converter = _get_marker_converter()
    if converter is None:
        logger.error("Marker converter unavailable (marker-pdf not installed?)")
        return {"total": len(ids), "ok": 0, "failed": ids, "skipped": [], "total_formulas": 0}

    ok = 0
    failed: list[str] = []
    skipped: list[str] = []
    total_formulas = 0

    for i, aid in enumerate(ids, 1):
        t0 = time.time()
        logger.info("[%d/%d] Re-extracting %s ...", i, len(ids), aid)
        try:
            result = reextract_fulltext(aid, resolved, converter=converter)
        except Exception:
            logger.exception("[%d/%d] Hard failure on %s", i, len(ids), aid)
            failed.append(aid)
            continue

        dt = time.time() - t0
        status = result.get("status")
        if status == "ok":
            ok += 1
            total_formulas += int(result.get("formulas") or 0)
            logger.info(
                "[%d/%d]   %s: %d chars, %d formulas (%.1fs)",
                i, len(ids), aid, result.get("chars", 0), result.get("formulas", 0), dt,
            )
        elif status == "skipped":
            skipped.append(aid)
            logger.info(
                "[%d/%d]   %s: skipped (%s)", i, len(ids), aid, result.get("reason"),
            )
        else:
            failed.append(aid)
            logger.error(
                "[%d/%d]   %s: failed (%s)", i, len(ids), aid, result.get("reason"),
            )

    return {
        "total": len(ids),
        "ok": ok,
        "failed": failed,
        "skipped": skipped,
        "total_formulas": total_formulas,
    }


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Re-extract fulltext.md for raw papers using Marker",
    )
    parser.add_argument(
        "arxiv_ids",
        nargs="*",
        help="Specific arXiv IDs to re-extract (default: all under wiki/raw/papers/)",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Process at most N papers (for smoke tests)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="List papers without running Marker",
    )
    args = parser.parse_args()

    summary = run(
        arxiv_ids=args.arxiv_ids or None,
        limit=args.limit,
        dry_run=args.dry_run,
    )
    logger.info("=" * 60)
    logger.info(
        "Summary: %d total, %d ok, %d failed, %d skipped, %d formulas total",
        summary["total"],
        summary["ok"],
        len(summary["failed"]),
        len(summary["skipped"]),
        summary["total_formulas"],
    )
    if summary["failed"]:
        logger.info("Failed: %s", ", ".join(summary["failed"]))
    return 0 if not summary["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
