"""Tests for daily_pipeline.py orchestrator."""

import pytest
from unittest.mock import patch, MagicMock
from scripts.daily_pipeline import format_feishu_message, collect_candidates
from scripts.taste_engine import ScoredPaper


def _make_scored(title: str, relevance: str, reason: str = "测试理由") -> ScoredPaper:
    paper = {
        "title": title,
        "url": "https://arxiv.org/abs/2604.00001",
        "authors": ["Alice"],
    }
    return ScoredPaper(
        paper=paper,
        relevance=relevance,
        reason=reason,
        embedding_score=0.5,
        source_level="llm",
    )


def test_format_feishu_message_with_high_and_medium():
    scored = [
        _make_scored("Paper A", "High", "高度相关"),
        _make_scored("Paper B", "Medium", "一般相关"),
    ]
    msg = format_feishu_message(scored, "2026-04-08")
    assert "📬" in msg
    assert "Paper A" in msg
    assert "Paper B" in msg
    assert "高度相关" in msg


def test_format_feishu_message_empty():
    msg = format_feishu_message([], "2026-04-08")
    assert "无新相关论文" in msg


def test_format_feishu_message_only_low():
    scored = [_make_scored("Paper C", "Low")]
    msg = format_feishu_message(scored, "2026-04-08")
    assert "无新相关论文" in msg


def test_format_feishu_message_with_project_url():
    paper = {
        "title": "Paper D",
        "url": "https://arxiv.org/abs/2604.00002",
        "authors": ["Bob"],
        "project_url": "https://github.com/bob/project",
    }
    scored = [
        ScoredPaper(
            paper=paper,
            relevance="High",
            reason="有项目链接",
            embedding_score=0.8,
            source_level="llm",
        )
    ]
    msg = format_feishu_message(scored, "2026-04-08")
    assert "项目" in msg
    assert "github.com/bob/project" in msg


def test_format_feishu_message_date_header():
    scored = [_make_scored("Paper E", "High")]
    msg = format_feishu_message(scored, "2026-04-08")
    assert "2026-04-08" in msg


def test_format_feishu_message_high_section_header():
    scored = [_make_scored("Paper F", "High")]
    msg = format_feishu_message(scored, "2026-04-08")
    assert "高相关" in msg


def test_format_feishu_message_medium_section_header():
    scored = [_make_scored("Paper G", "Medium")]
    msg = format_feishu_message(scored, "2026-04-08")
    assert "可能感兴趣" in msg


@patch("scripts.daily_pipeline.fetch_all_feeds", return_value=[])
@patch("scripts.daily_pipeline.search_semantic_scholar", return_value=[])
@patch("scripts.daily_pipeline.search_arxiv")
@patch("scripts.daily_pipeline.deduplicate")
@patch("scripts.daily_pipeline.load_feeds", return_value=[])
@patch("scripts.daily_pipeline.load_active_topics", return_value=[])
def test_collect_candidates_deduplicates(
    mock_topics, mock_feeds, mock_dedup, mock_arxiv, mock_s2, mock_rss
):
    mock_arxiv.return_value = [{"title": "Paper 1", "arxiv_id": "2604.1"}]
    mock_dedup.return_value = [{"title": "Paper 1", "arxiv_id": "2604.1"}]
    config = {"semantic_scholar": {"api_key": ""}}
    result = collect_candidates(config, {})
    mock_dedup.assert_called_once()
    assert len(result) == 1


@patch("scripts.daily_pipeline.fetch_all_feeds", return_value=[])
@patch("scripts.daily_pipeline.search_semantic_scholar", return_value=[])
@patch("scripts.daily_pipeline.search_arxiv", return_value=[])
@patch("scripts.daily_pipeline.deduplicate", return_value=[])
@patch("scripts.daily_pipeline.load_feeds", return_value=[])
@patch("scripts.daily_pipeline.load_active_topics")
def test_collect_candidates_per_topic_search(
    mock_topics, mock_feeds, mock_dedup, mock_arxiv, mock_s2, mock_rss
):
    mock_topics.return_value = [
        {
            "keywords": ["dexterous manipulation"],
            "arxiv_categories": ["cs.RO"],
            "semantic_scholar_fields": ["Computer Science"],
        }
    ]
    mock_dedup.return_value = []
    config = {"semantic_scholar": {"api_key": "test-key"}}
    collect_candidates(config, {})
    # Broad search (1 call) + per-topic arXiv (1 call) = 2 arXiv calls
    assert mock_arxiv.call_count == 2
    # Per-topic S2 = 1 call
    assert mock_s2.call_count == 1


@patch("scripts.daily_pipeline.fetch_all_feeds")
@patch("scripts.daily_pipeline.search_semantic_scholar", return_value=[])
@patch("scripts.daily_pipeline.search_arxiv", return_value=[])
@patch("scripts.daily_pipeline.deduplicate", return_value=[])
@patch("scripts.daily_pipeline.load_feeds")
@patch("scripts.daily_pipeline.load_active_topics", return_value=[])
def test_collect_candidates_includes_rss(
    mock_topics, mock_feeds, mock_dedup, mock_arxiv, mock_s2, mock_rss
):
    mock_feeds.return_value = [{"url": "https://example.com/feed", "name": "Test Blog"}]
    mock_rss.return_value = [{"title": "Blog Post", "url": "https://example.com/post"}]
    mock_dedup.return_value = [{"title": "Blog Post", "url": "https://example.com/post"}]
    config = {"semantic_scholar": {"api_key": ""}}
    result = collect_candidates(config, {})
    mock_rss.assert_called_once()
    assert len(result) == 1
