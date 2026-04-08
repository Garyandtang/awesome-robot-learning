"""Tests for scripts/taste_engine.py — three-level recommendation funnel."""

import pytest
from unittest.mock import patch, MagicMock

from scripts.taste_engine import (
    hard_rule_filter,
    embedding_rank,
    _build_llm_prompt,
    filter_candidates,
    ScoredPaper,
)


SAMPLE_TASTE = {
    "preferences": {"like": ["locomotion"], "dislike": ["medical"]},
    "authors_whitelist": [{"name": "Pieter Abbeel"}],
    "hard_rules": {
        "positive_keywords": [
            "humanoid",
            "manipulation",
            "locomotion",
            "reinforcement learning",
        ],
        "negative_keywords": ["medical imaging", "drug discovery"],
        "author_boost": ["Pieter Abbeel"],
    },
    "stats": {"total_collected": 510},
}


def _make_paper(title, abstract="", authors=None):
    return {
        "title": title,
        "abstract": abstract,
        "authors": authors or [],
        "arxiv_id": "2604.00001",
        "url": "https://arxiv.org/abs/2604.00001",
    }


# === Level 1 Tests ===


def test_hard_rule_filter_passes_positive_keyword():
    papers = [_make_paper("Humanoid Robot Locomotion")]
    result = hard_rule_filter(papers, SAMPLE_TASTE)
    assert len(result) == 1


def test_hard_rule_filter_rejects_negative_keyword():
    papers = [_make_paper("Medical Imaging with Deep Learning")]
    result = hard_rule_filter(papers, SAMPLE_TASTE)
    assert len(result) == 0


def test_hard_rule_filter_rejects_no_keyword_match():
    papers = [_make_paper("Quantum Computing Advances")]
    result = hard_rule_filter(papers, SAMPLE_TASTE)
    assert len(result) == 0


def test_hard_rule_filter_author_boost():
    papers = [_make_paper("Some Random Title", authors=["Pieter Abbeel"])]
    result = hard_rule_filter(papers, SAMPLE_TASTE)
    assert len(result) == 1
    assert result[0].get("_author_boost") is True


def test_hard_rule_filter_negative_overrides_positive():
    papers = [_make_paper("Medical Imaging for Humanoid Robots")]
    result = hard_rule_filter(papers, SAMPLE_TASTE)
    assert len(result) == 0


def test_hard_rule_filter_case_insensitive():
    papers = [_make_paper("HUMANOID robot LOCOMOTION")]
    result = hard_rule_filter(papers, SAMPLE_TASTE)
    assert len(result) == 1


# === Level 2 Tests (mocked encoder) ===


@patch("scripts.taste_engine.rank_candidates")
def test_embedding_rank_returns_top_k(mock_rank, tmp_path):
    papers = [_make_paper(f"Paper {i}") for i in range(50)]
    mock_rank.return_value = [
        {**_make_paper(f"Paper {i}"), "_embedding_score": 0.9 - i * 0.01}
        for i in range(30)
    ]
    result = embedding_rank(papers, tmp_path, top_k=30)
    assert len(result) == 30
    assert "_embedding_score" in result[0]


@patch("scripts.taste_engine.rank_candidates")
def test_embedding_rank_preserves_author_boost(mock_rank, tmp_path):
    papers = [_make_paper(f"Paper {i}") for i in range(10)]
    papers[5]["_author_boost"] = True
    mock_rank.return_value = [
        {**_make_paper(f"Paper {i}"), "_embedding_score": 0.5 - i * 0.05}
        for i in range(5)
    ]
    result = embedding_rank(papers, tmp_path, top_k=5)
    boosted = [p for p in result if p.get("_author_boost")]
    assert len(boosted) >= 1


# === LLM Prompt Tests ===


def test_build_llm_prompt_includes_papers():
    papers = [_make_paper("Humanoid Walking", abstract="We propose a method...")]
    prompt = _build_llm_prompt(papers, SAMPLE_TASTE, [])
    assert "Humanoid Walking" in prompt
    assert "We propose a method" in prompt


def test_build_llm_prompt_includes_wiki_concepts():
    papers = [_make_paper("Test")]
    prompt = _build_llm_prompt(
        papers, SAMPLE_TASTE, ["Diffusion Policy", "Sim-to-Real Transfer"]
    )
    assert "Diffusion Policy" in prompt
    assert "Sim-to-Real Transfer" in prompt


def test_build_llm_prompt_includes_taste_preferences():
    papers = [_make_paper("Test")]
    prompt = _build_llm_prompt(papers, SAMPLE_TASTE, [])
    assert "locomotion" in prompt
    assert "medical" in prompt


# === Integration Test (mocked LLM) ===


@patch("scripts.taste_engine.subprocess.run")
@patch("scripts.taste_engine.rank_candidates")
def test_filter_candidates_full_pipeline(mock_rank, mock_run, tmp_path):
    mock_rank.return_value = [
        {
            **_make_paper(
                "Humanoid Locomotion with RL",
                abstract="A new method for humanoid",
            ),
            "_embedding_score": 0.8,
        },
        {
            **_make_paper(
                "Robot Manipulation via Diffusion",
                abstract="Diffusion policy for manipulation",
            ),
            "_embedding_score": 0.6,
        },
    ]
    mock_run.return_value = MagicMock(
        stdout='[{"index": 1, "relevance": "High", "reason": "测试推荐理由"}, '
        '{"index": 2, "relevance": "Medium", "reason": "一般相关"}]',
        returncode=0,
    )
    papers = [
        _make_paper(
            "Humanoid Locomotion with RL", abstract="A new method for humanoid"
        ),
        _make_paper(
            "Robot Manipulation via Diffusion",
            abstract="Diffusion policy for manipulation",
        ),
    ]
    results = filter_candidates(papers, SAMPLE_TASTE, tmp_path)
    assert len(results) >= 1
    assert all(isinstance(r, ScoredPaper) for r in results)
    high = [r for r in results if r.relevance == "High"]
    assert len(high) >= 1
    assert "测试" in high[0].reason
