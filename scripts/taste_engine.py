"""Three-level paper recommendation funnel.

Level 1: Hard rules (zero cost) - keyword/author filtering
Level 2: Embedding similarity (local) - semantic ranking
Level 3: LLM taste scoring (top 30 only) - Claude CLI evaluation
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from scripts.config import load_embedding_config
from scripts.embedding_store import (
    compute_time_decay_weights,
    encode_texts,
    load_corpus,
    rank_candidates,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScoredPaper:
    """Immutable scored paper result from the recommendation funnel."""

    paper: dict
    relevance: str  # "High" | "Medium" | "Low"
    reason: str  # Chinese recommendation reason
    embedding_score: float  # Level 2 similarity score (0.0 if skipped)
    source_level: str  # Which level determined final score


# ---------------------------------------------------------------------------
# Level 1: Hard rule filter (zero cost)
# ---------------------------------------------------------------------------


def hard_rule_filter(
    candidates: list[dict], taste_profile: dict
) -> list[dict]:
    """Filter candidates using keyword and author rules.

    - Author whitelist -> auto-pass, tag _author_boost = True
    - Positive keyword match (title OR abstract, case-insensitive) -> pass
    - Negative keyword match (title OR abstract, case-insensitive) -> reject
    - Negative overrides positive
    - No keyword match at all -> reject
    """
    hard_rules = taste_profile.get("hard_rules", {})
    positive_keywords = [
        kw.lower() for kw in hard_rules.get("positive_keywords", [])
    ]
    negative_keywords = [
        kw.lower() for kw in hard_rules.get("negative_keywords", [])
    ]
    author_boost_list = [
        name.lower() for name in hard_rules.get("author_boost", [])
    ]

    passed: list[dict] = []

    for paper in candidates:
        title = paper.get("title", "")
        abstract = paper.get("abstract", "")
        text = f"{title} {abstract}".lower()
        authors = paper.get("authors", [])

        # Check author whitelist
        is_boosted = any(
            a.lower() in author_boost_list for a in authors
        )

        # Check negative keywords
        has_negative = any(kw in text for kw in negative_keywords)

        # Check positive keywords
        has_positive = any(kw in text for kw in positive_keywords)

        # Negative overrides everything (including author boost for keyword match)
        if has_negative:
            continue

        # Author boost -> auto-pass
        if is_boosted:
            passed.append({**paper, "_author_boost": True})
            continue

        # Positive keyword match -> pass
        if has_positive:
            passed.append(dict(paper))
            continue

        # No match -> reject

    logger.info(
        "Level 1 hard_rule_filter: %d -> %d candidates",
        len(candidates),
        len(passed),
    )
    return passed


# ---------------------------------------------------------------------------
# Level 2: Embedding rank (local)
# ---------------------------------------------------------------------------


def embedding_rank(
    candidates: list[dict],
    corpus_dir: Path,
    top_k: int = 30,
) -> list[dict]:
    """Rank candidates by embedding similarity to the taste corpus.

    Falls back to returning candidates without scores if:
    - corpus is too small (< corpus_min_for_ranking)
    - sentence_transformers is not installed
    """
    if not candidates:
        return []

    corpus_dir = Path(corpus_dir)

    # Load embedding config for minimum corpus size
    try:
        emb_config = load_embedding_config()
    except Exception as exc:
        logger.warning("Failed to load embedding config, using defaults: %s", exc)
        emb_config = {"corpus_min_for_ranking": 10}

    corpus_min = emb_config.get("corpus_min_for_ranking", 10)

    # Load corpus embeddings
    corpus_embeddings, corpus_metadata = load_corpus(corpus_dir)

    corpus_size = len(corpus_metadata) if corpus_metadata else 0
    has_corpus = (
        corpus_embeddings is not None
        and corpus_embeddings.size > 0
        and corpus_size >= corpus_min
    )

    if not has_corpus:
        logger.info(
            "Level 2: corpus too small (%d < %d), skipping embedding rank",
            corpus_size,
            corpus_min,
        )
        return _fallback_sort(candidates, top_k)

    # Try encoding candidates
    try:
        texts = [
            f"{p.get('title', '')}. {p.get('abstract', '')}"
            for p in candidates
        ]
        candidate_embeddings = encode_texts(texts)
    except Exception:
        logger.warning(
            "Level 2: sentence_transformers not available, falling back"
        )
        return _fallback_sort(candidates, top_k)

    # Compute time decay weights and rank
    time_weights = compute_time_decay_weights(corpus_embeddings.shape[0])
    ranked = rank_candidates(
        candidates,
        candidate_embeddings,
        corpus_embeddings,
        top_k=top_k,
        time_weights=time_weights,
    )

    # Ensure author_boost papers are preserved
    ranked_titles = {p.get("title") for p in ranked}
    boosted_missing = [
        p
        for p in candidates
        if p.get("_author_boost") and p.get("title") not in ranked_titles
    ]
    for paper in boosted_missing:
        ranked.append({**paper, "_embedding_score": 0.0})

    logger.info(
        "Level 2 embedding_rank: %d -> %d candidates (top_k=%d)",
        len(candidates),
        len(ranked),
        top_k,
    )
    return ranked


def _fallback_sort(candidates: list[dict], top_k: int) -> list[dict]:
    """Sort candidates with author_boost first, assign zero embedding scores."""
    boosted = [p for p in candidates if p.get("_author_boost")]
    rest = [p for p in candidates if not p.get("_author_boost")]
    sorted_candidates = boosted + rest
    return [
        {**p, "_embedding_score": 0.0} for p in sorted_candidates[:top_k]
    ]


# ---------------------------------------------------------------------------
# Level 3: LLM taste scoring
# ---------------------------------------------------------------------------


def _build_llm_prompt(
    papers: list[dict],
    taste_profile: dict,
    wiki_concepts: list[str],
) -> str:
    """Build the Chinese prompt for LLM taste scoring."""
    prefs = taste_profile.get("preferences", {})
    likes = ", ".join(prefs.get("like", []))
    dislikes = ", ".join(prefs.get("dislike", []))

    hard_rules = taste_profile.get("hard_rules", {})
    pos_kw = ", ".join(hard_rules.get("positive_keywords", []))

    # Wiki concept block (optional)
    concept_block = ""
    if wiki_concepts:
        concept_list = "\n".join(f"  - {c}" for c in wiki_concepts)
        concept_block = f"\n- 知识库概念索引:\n{concept_list}"

    # Paper entries
    paper_entries = []
    for i, paper in enumerate(papers, start=1):
        title = paper.get("title", "")
        abstract = paper.get("abstract", "")
        authors = ", ".join(paper.get("authors", []))
        emb_score = paper.get("_embedding_score", 0.0)
        is_boosted = paper.get("_author_boost", False)
        boost_tag = " [作者白名单]" if is_boosted else ""

        entry = (
            f"### 论文 {i}{boost_tag}\n"
            f"- 标题: {title}\n"
            f"- 作者: {authors}\n"
            f"- 摘要: {abstract}\n"
            f"- 嵌入相似度: {emb_score:.3f}"
        )
        paper_entries.append(entry)

    papers_text = "\n\n".join(paper_entries)

    prompt = (
        "你是一个机器人学习领域的论文推荐系统。根据用户的研究品味对以下论文进行评分。\n"
        "\n"
        "## 用户研究偏好\n"
        f"- 喜欢的方向: {likes}\n"
        f"- 不喜欢的方向: {dislikes}\n"
        f"- 关注的关键词: {pos_kw}"
        f"{concept_block}\n"
        "\n"
        "## 待评分论文\n"
        "\n"
        f"{papers_text}\n"
        "\n"
        "## 评分要求\n"
        "\n"
        "对每篇论文输出严格的 JSON 数组，每个元素格式如下：\n"
        '```json\n'
        '{"index": 1, "relevance": "High", "reason": "..."}\n'
        '```\n'
        "\n"
        "评分标准：\n"
        "- **High**: 直接相关于用户的活跃研究方向，方法或问题设置有重要创新\n"
        "- **Medium**: 与机器人学习广泛相关，部分匹配用户偏好\n"
        "- **Low**: 不相关或匹配用户不喜欢的方向\n"
        "\n"
        "注意：\n"
        "1. reason 必须用中文\n"
        "2. reason 要具体说明为什么推荐\n"
        "3. 作者白名单匹配的论文，评分不应低于 Medium\n"
        "4. 嵌入相似度高（>0.5）的论文，请仔细审阅再评分\n"
        "5. 只输出 JSON 数组，不要输出其他内容"
    )

    return prompt


def llm_taste_score(
    papers: list[dict],
    taste_profile: dict,
    wiki_concept_index: list[str] | None = None,
) -> list[ScoredPaper]:
    """Score papers using Claude CLI (Level 3).

    Calls `claude --print -p <prompt>` and parses JSON output.
    Falls back to Medium relevance on parse failure.
    """
    if not papers:
        return []

    wiki_concepts = wiki_concept_index or []
    prompt = _build_llm_prompt(papers, taste_profile, wiki_concepts)

    try:
        result = subprocess.run(
            ["claude", "--print", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            logger.warning(
                "Claude CLI exited with code %d: %s",
                result.returncode,
                result.stderr.strip()[:200],
            )
            return _fallback_llm_scores(papers)
        raw_output = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.warning("LLM scoring failed: %s", exc)
        return _fallback_llm_scores(papers)

    # Parse JSON — handle ```json ... ``` wrapping
    json_text = _extract_json(raw_output)

    try:
        scores = json.loads(json_text)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse LLM output, using fallback scores")
        return _fallback_llm_scores(papers)

    if not isinstance(scores, list):
        logger.warning("LLM returned non-list JSON, using fallback scores")
        return _fallback_llm_scores(papers)

    VALID_RELEVANCE = {"High", "Medium", "Low"}

    scored_papers: list[ScoredPaper] = []
    for entry in scores:
        idx = entry.get("index", 0) - 1  # 1-indexed -> 0-indexed
        if 0 <= idx < len(papers):
            raw_relevance = entry.get("relevance", "Medium")
            relevance = raw_relevance if raw_relevance in VALID_RELEVANCE else "Medium"
            scored_papers.append(
                ScoredPaper(
                    paper=papers[idx],
                    relevance=relevance,
                    reason=entry.get("reason", "LLM评分"),
                    embedding_score=papers[idx].get("_embedding_score", 0.0),
                    source_level="llm",
                )
            )

    # Fill any missing papers with Medium
    scored_indices = {sp.paper.get("title") for sp in scored_papers}
    for paper in papers:
        if paper.get("title") not in scored_indices:
            scored_papers.append(
                ScoredPaper(
                    paper=paper,
                    relevance="Medium",
                    reason="LLM未返回评分，默认中等",
                    embedding_score=paper.get("_embedding_score", 0.0),
                    source_level="llm",
                )
            )

    logger.info("Level 3 LLM scoring: %d papers scored", len(scored_papers))
    return scored_papers


def _extract_json(raw: str) -> str:
    """Extract JSON array from raw LLM output, handling ```json fences."""
    # Try to find ```json ... ``` block
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Otherwise return the raw text (might be valid JSON already)
    return raw


def _fallback_llm_scores(papers: list[dict]) -> list[ScoredPaper]:
    """Return Medium scores for all papers when LLM fails."""
    return [
        ScoredPaper(
            paper=paper,
            relevance="Medium",
            reason="LLM评分不可用，默认中等相关",
            embedding_score=paper.get("_embedding_score", 0.0),
            source_level="llm_fallback",
        )
        for paper in papers
    ]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def filter_candidates(
    candidates: list[dict],
    taste_profile: dict,
    corpus_dir: Path,
    wiki_path: Path | None = None,
    top_k: int = 30,
) -> list[ScoredPaper]:
    """Three-level paper recommendation funnel.

    Level 1: Hard rules (zero cost)
    Level 2: Embedding similarity (local)
    Level 3: LLM taste scoring (top 30 only)
    """
    if not candidates:
        return []

    # Level 1: Hard rule filtering
    passed_l1 = hard_rule_filter(candidates, taste_profile)
    logger.info("Funnel L1: %d -> %d", len(candidates), len(passed_l1))

    if not passed_l1:
        return []

    # Level 2: Embedding ranking
    ranked_l2 = embedding_rank(passed_l1, corpus_dir, top_k=top_k)
    logger.info("Funnel L2: %d -> %d", len(passed_l1), len(ranked_l2))

    if not ranked_l2:
        return []

    # Extract wiki concept names for Level 3 prompt
    wiki_concepts: list[str] = []
    if wiki_path is not None:
        wiki_path = Path(wiki_path)
        if wiki_path.is_dir():
            try:
                from scripts.wiki_compiler import get_concept_index

                wiki_concepts = get_concept_index(wiki_dir=wiki_path)
            except ImportError:
                wiki_concepts = _extract_wiki_concepts(wiki_path)

    # Level 3: LLM taste scoring
    results = llm_taste_score(ranked_l2, taste_profile, wiki_concepts)
    logger.info("Funnel L3: %d papers scored", len(results))

    return results


def _extract_wiki_concepts(wiki_path: Path) -> list[str]:
    """Extract concept names from wiki directory (markdown filenames)."""
    concepts: list[str] = []
    for md_file in sorted(wiki_path.glob("*.md")):
        # Convert filename to concept name: "Diffusion-Policy.md" -> "Diffusion Policy"
        name = md_file.stem.replace("-", " ").replace("_", " ")
        if name.lower() not in ("readme", "index", "home"):
            concepts.append(name)
    return concepts
