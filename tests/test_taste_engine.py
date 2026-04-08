"""Tests for scripts/taste_engine.py — three-level recommendation funnel."""

import subprocess

import pytest
from unittest.mock import patch, MagicMock

from scripts.taste_engine import (
    hard_rule_filter,
    embedding_rank,
    llm_taste_score,
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


@patch("scripts.taste_engine.compute_time_decay_weights")
@patch("scripts.taste_engine.encode_texts")
@patch("scripts.taste_engine.load_corpus")
@patch("scripts.taste_engine.rank_candidates")
def test_embedding_rank_returns_top_k(
    mock_rank, mock_load, mock_encode, mock_weights, tmp_path
):
    import numpy as np

    mock_load.return_value = (np.zeros((20, 768)), [{}] * 20)
    mock_encode.return_value = np.zeros((50, 768))
    mock_weights.return_value = np.ones(20) / 20
    mock_rank.return_value = [
        {**_make_paper(f"Paper {i}"), "_embedding_score": 0.9 - i * 0.01}
        for i in range(30)
    ]
    papers = [_make_paper(f"Paper {i}") for i in range(50)]
    result = embedding_rank(papers, tmp_path, top_k=30)
    assert len(result) == 30
    assert mock_rank.called
    assert result[0]["_embedding_score"] == pytest.approx(0.9)


@patch("scripts.taste_engine.compute_time_decay_weights")
@patch("scripts.taste_engine.encode_texts")
@patch("scripts.taste_engine.load_corpus")
@patch("scripts.taste_engine.rank_candidates")
def test_embedding_rank_preserves_author_boost(
    mock_rank, mock_load, mock_encode, mock_weights, tmp_path
):
    import numpy as np

    mock_load.return_value = (np.zeros((20, 768)), [{}] * 20)
    mock_encode.return_value = np.zeros((10, 768))
    mock_weights.return_value = np.ones(20) / 20
    # rank_candidates returns top 5 — paper 5 (boosted) is NOT in this list
    mock_rank.return_value = [
        {**_make_paper(f"Paper {i}"), "_embedding_score": 0.5 - i * 0.05}
        for i in range(5)
    ]
    papers = [_make_paper(f"Paper {i}") for i in range(10)]
    papers[5]["_author_boost"] = True
    result = embedding_rank(papers, tmp_path, top_k=5)
    assert mock_rank.called
    boosted = [p for p in result if p.get("_author_boost")]
    assert len(boosted) == 1
    assert boosted[0]["title"] == "Paper 5"


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


# === Level 3 Tests (llm_taste_score) ===


@patch("scripts.taste_engine.subprocess.run")
def test_llm_taste_score_successful_json_parse(mock_run):
    papers = [
        {**_make_paper("Paper A", abstract="About locomotion"), "_embedding_score": 0.8},
        {**_make_paper("Paper B", abstract="About manipulation"), "_embedding_score": 0.6},
    ]
    mock_run.return_value = MagicMock(
        stdout='[{"index": 1, "relevance": "High", "reason": "直接相关"}, '
        '{"index": 2, "relevance": "Low", "reason": "不太相关"}]',
        returncode=0,
    )
    results = llm_taste_score(papers, SAMPLE_TASTE)
    assert len(results) == 2
    assert all(isinstance(r, ScoredPaper) for r in results)
    assert results[0].relevance == "High"
    assert results[0].reason == "直接相关"
    assert results[0].embedding_score == pytest.approx(0.8)
    assert results[0].source_level == "llm"
    assert results[1].relevance == "Low"
    assert results[1].reason == "不太相关"


@patch("scripts.taste_engine.subprocess.run")
def test_llm_taste_score_parse_failure_fallback(mock_run):
    papers = [
        {**_make_paper("Paper A"), "_embedding_score": 0.5},
        {**_make_paper("Paper B"), "_embedding_score": 0.3},
    ]
    mock_run.return_value = MagicMock(
        stdout="this is not valid json at all {{{{",
        returncode=0,
    )
    results = llm_taste_score(papers, SAMPLE_TASTE)
    assert len(results) == 2
    assert all(isinstance(r, ScoredPaper) for r in results)
    assert all(r.relevance == "Medium" for r in results)
    assert all(r.source_level == "llm_fallback" for r in results)


@patch("scripts.taste_engine.subprocess.run")
def test_llm_taste_score_subprocess_timeout_fallback(mock_run):
    papers = [
        {**_make_paper("Paper A"), "_embedding_score": 0.7},
    ]
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=300)
    results = llm_taste_score(papers, SAMPLE_TASTE)
    assert len(results) == 1
    assert results[0].relevance == "Medium"
    assert results[0].source_level == "llm_fallback"


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
    assert len(results) == 2
    assert all(isinstance(r, ScoredPaper) for r in results)
    high = [r for r in results if r.relevance == "High"]
    assert len(high) >= 1
    assert "测试" in high[0].reason
