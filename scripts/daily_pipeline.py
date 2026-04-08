"""Daily paper recommendation pipeline orchestrator."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path

from scripts.config import (
    load_active_topics,
    load_config,
    load_feeds,
    load_taste_profile,
    get_wiki_path,
)
from scripts.search_papers import (
    build_arxiv_query,
    build_s2_query,
    deduplicate,
    load_seen,
    save_seen,
    search_arxiv,
    search_semantic_scholar,
)
from scripts.rss_fetcher import fetch_all_feeds
from scripts.taste_engine import filter_candidates, ScoredPaper

logger = logging.getLogger(__name__)


def collect_candidates(config: dict, seen: dict) -> list[dict]:
    """Run all source layers and return deduplicated candidates.

    1. Broad arXiv search (cs.RO, cs.AI, max_results=100, days_back=2)
    2. Per-topic targeted search (arXiv + Semantic Scholar)
    3. RSS feed search (days_back=7)
    4. Deduplicate against seen papers
    """
    topics = load_active_topics()
    all_papers: list[dict] = []

    # Broad arXiv search
    broad_query = build_arxiv_query(["cs.RO", "cs.AI"])
    all_papers.extend(search_arxiv(broad_query, max_results=100, days_back=2))

    # Per-topic targeted search
    for topic in topics:
        kws = topic.get("keywords", [])
        cats = topic.get("arxiv_categories", ["cs.RO"])
        q = build_arxiv_query(cats, kws)
        all_papers.extend(search_arxiv(q, max_results=50, days_back=2))

        s2q = build_s2_query(kws)
        fields = topic.get("semantic_scholar_fields")
        s2_key = config.get("semantic_scholar", {}).get("api_key", "")
        all_papers.extend(
            search_semantic_scholar(
                s2q, fields, 30, str(datetime.now().year), s2_key
            )
        )

    # RSS feeds
    feeds = load_feeds()
    rss_papers = fetch_all_feeds(feeds, seen, days_back=7)
    all_papers.extend(rss_papers)

    # Deduplicate
    return deduplicate(all_papers, seen)


def format_feishu_message(scored: list[ScoredPaper], date_str: str) -> str:
    """Format scored papers into the Feishu message template (Chinese).

    Format:
    📬 今日论文推荐（YYYY-MM-DD）

    ⭐ 高相关

    Paper Title
    方法：reason from ScoredPaper
    链接：url
    项目：project_url（如有）

    📎 可能感兴趣

    Paper Title — reason
    链接：url

    If no papers: '📬 今日无新相关论文。'
    """
    if not scored:
        return "📬 今日无新相关论文。"

    high = [s for s in scored if s.relevance == "High"]
    medium = [s for s in scored if s.relevance == "Medium"]

    if not high and not medium:
        return "📬 今日无新相关论文。"

    lines: list[str] = [f"📬 今日论文推荐（{date_str}）\n"]

    if high:
        lines.append("⭐ 高相关\n")
        for s in high:
            p = s.paper
            authors = ", ".join(p.get("authors", []))
            lines.append(f"{p.get('title', '未知标题')}")
            if authors:
                lines.append(f"作者：{authors}")
            lines.append(f"方法：{s.reason}")
            lines.append(f"链接：{p.get('url', '')}")
            if p.get("project_url"):
                lines.append(f"项目：{p['project_url']}")
            lines.append("")

    if medium:
        lines.append("📎 可能感兴趣\n")
        for s in medium:
            p = s.paper
            authors = ", ".join(p.get("authors", []))
            lines.append(f"{p.get('title', '未知标题')}")
            if authors:
                lines.append(f"作者：{authors}")
            lines.append(f"方法：{s.reason}")
            lines.append(f"链接：{p.get('url', '')}")
            lines.append("")

    return "\n".join(lines)


def run_daily_pipeline() -> dict:
    """Run the complete daily pipeline.

    1. Load config and seen papers
    2. Collect candidates from all sources
    3. Run taste_engine.filter_candidates()
    4. Format Feishu message
    5. Update seen_papers.json
    6. Return stats
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )

    config = load_config()
    repo_path = Path(config["awesome_repo"]["path"])
    seen_path = repo_path / "data" / "seen_papers.json"
    corpus_dir = repo_path / "data" / "embeddings"

    seen = load_seen(seen_path)
    taste_profile = load_taste_profile()

    # Step 1: Collect candidates
    candidates = collect_candidates(config, seen)
    logger.info("Collected %d candidates", len(candidates))

    if not candidates:
        message = "📬 今日无新相关论文。"
        return {
            "candidates_found": 0,
            "scored_count": 0,
            "high_count": 0,
            "medium_count": 0,
            "low_count": 0,
            "message": message,
        }

    # Step 2: Run taste engine
    wiki_path = None
    try:
        wiki_path = get_wiki_path()
    except Exception:
        pass

    scored = filter_candidates(
        candidates, taste_profile, corpus_dir, wiki_path=wiki_path
    )

    # Step 3: Format message
    date_str = date.today().isoformat()
    message = format_feishu_message(scored, date_str)

    # Step 4: Update seen papers
    for paper in candidates:
        paper_id = paper.get("arxiv_id") or paper.get("url", "")
        if paper.get("source_type") == "rss":
            paper_id = f"rss:{paper_id}"
        seen[paper_id] = date.today().isoformat()
    save_seen(seen_path, seen)

    high = [s for s in scored if s.relevance == "High"]
    medium = [s for s in scored if s.relevance == "Medium"]
    low = [s for s in scored if s.relevance == "Low"]

    return {
        "candidates_found": len(candidates),
        "scored_count": len(scored),
        "high_count": len(high),
        "medium_count": len(medium),
        "low_count": len(low),
        "message": message,
    }
