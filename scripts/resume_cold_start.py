"""Resume Task 2 cold-start compile after the 529 crash.

Compiles any paper in wiki/raw/papers/ that does not yet have a
wiki/papers/{arxiv_id}.md page, one at a time, with exponential backoff
on Claude CLI errors (especially 529 Overloaded). Writes progress to
resume_cold_start.log and bumps the final index + topic map at the end.

Usage:
    PYTHONPATH= PYTHONNOUSERSITE=1 python3 -m scripts.resume_cold_start
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from scripts.wiki_compiler import (
    build_index_pages,
    compile_paper_v2,
    rebuild_topic_map_llm,
)

WIKI_DIR = Path("wiki")
LOG_FILE = Path("resume_cold_start.log")

MAX_RETRIES = 6  # 6 attempts per paper
BASE_DELAY = 60  # seconds; doubles each retry → 60, 120, 240, 480, 960, 1920 (~32m max)


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("resume_cold_start")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


def remaining_papers(wiki_dir: Path) -> list[str]:
    raw_dir = wiki_dir / "raw" / "papers"
    papers_dir = wiki_dir / "papers"
    all_ids: list[str] = []
    for p in sorted(raw_dir.iterdir()):
        if not p.is_dir():
            continue
        if (p / "meta.yaml").exists() and (p / "fulltext.md").exists():
            all_ids.append(p.name)
    done = {
        f.stem for f in papers_dir.glob("*.md") if f.name != "INDEX.md"
    }
    # Only resume papers that don't yet have a wiki page
    return [i for i in all_ids if i not in done]


def compile_with_retries(arxiv_id: str, wiki_dir: Path, logger: logging.Logger) -> bool:
    delay = BASE_DELAY
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info("[%s] attempt %d/%d", arxiv_id, attempt, MAX_RETRIES)
            start = time.monotonic()
            result = compile_paper_v2(arxiv_id, wiki_dir)
            elapsed = time.monotonic() - start
            logger.info(
                "[%s] DONE in %.1fs: page=%s, concepts_created=%d, concepts_updated=%d",
                arxiv_id,
                elapsed,
                result["paper_page"].name,
                result["concepts_created"],
                result["concepts_updated"],
            )
            return True
        except Exception as exc:  # noqa: BLE001 — intentional broad catch for retry
            msg = str(exc)
            is_overload = "529" in msg or "overloaded" in msg.lower()
            logger.warning(
                "[%s] attempt %d failed: %s: %s%s",
                arxiv_id,
                attempt,
                type(exc).__name__,
                msg[:200],
                " (529 overloaded)" if is_overload else "",
            )
            if attempt == MAX_RETRIES:
                logger.error("[%s] GIVING UP after %d attempts", arxiv_id, MAX_RETRIES)
                return False
            sleep_for = delay
            logger.info("[%s] sleeping %ds before retry", arxiv_id, sleep_for)
            time.sleep(sleep_for)
            delay = min(delay * 2, 1920)
    return False


def main() -> int:
    logger = setup_logging()
    logger.info("========== resume_cold_start starting ==========")
    logger.info("now: %s", datetime.now().isoformat())

    pending = remaining_papers(WIKI_DIR)
    logger.info("Pending papers (%d): %s", len(pending), pending)

    if not pending:
        logger.info("Nothing to compile. Will still rebuild indexes + topic map.")
    else:
        succeeded: list[str] = []
        failed: list[str] = []
        for idx, arxiv_id in enumerate(pending, start=1):
            logger.info("[%d/%d] starting %s", idx, len(pending), arxiv_id)
            ok = compile_with_retries(arxiv_id, WIKI_DIR, logger)
            if ok:
                succeeded.append(arxiv_id)
            else:
                failed.append(arxiv_id)
            # short rate-limit pause between papers
            if idx < len(pending):
                time.sleep(3)

        logger.info("---- compile phase done ----")
        logger.info("succeeded (%d): %s", len(succeeded), succeeded)
        logger.info("failed (%d): %s", len(failed), failed)

    logger.info("---- rebuilding indexes ----")
    try:
        build_index_pages(WIKI_DIR)
        logger.info("build_index_pages OK")
    except Exception:
        logger.exception("build_index_pages FAILED")

    logger.info("---- rebuilding TOPIC-MAP via LLM ----")
    try:
        path = rebuild_topic_map_llm(WIKI_DIR)
        logger.info("rebuild_topic_map_llm OK: %s", path)
    except Exception:
        logger.exception("rebuild_topic_map_llm FAILED")

    logger.info("========== resume_cold_start finished ==========")
    return 0


if __name__ == "__main__":
    sys.exit(main())
