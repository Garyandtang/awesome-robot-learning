"""Tests for scripts/embedding_store.py."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from scripts.embedding_store import (
    compute_time_decay_weights,
    compute_similarity_scores,
    encode_texts,
    load_embeddings,
    save_embeddings,
    append_to_corpus,
    rank_candidates,
    load_corpus,
)


class TestTimeDecayWeights:
    def test_single_item(self):
        weights = compute_time_decay_weights(1)
        assert len(weights) == 1
        assert np.isclose(weights[0], 1.0)

    def test_decreasing_weights(self):
        weights = compute_time_decay_weights(10)
        assert len(weights) == 10
        assert weights[0] > weights[-1]
        assert np.isclose(weights.sum(), 1.0)

    def test_formula_matches_zotero_arxiv_daily(self):
        n = 5
        weights = compute_time_decay_weights(n)
        expected_raw = 1.0 / (1.0 + np.log10(np.arange(n) + 1))
        expected = expected_raw / expected_raw.sum()
        np.testing.assert_array_almost_equal(weights, expected)

    def test_zero_items(self):
        weights = compute_time_decay_weights(0)
        assert len(weights) == 0

    def test_date_based_newer_papers_higher_weight(self):
        metadata = [
            {"date": "2026.03"},  # newest
            {"date": "2025.06"},
            {"date": "2024.01"},
            {"date": "2020.01"},  # oldest
        ]
        weights = compute_time_decay_weights(4, metadata=metadata)
        assert len(weights) == 4
        assert np.isclose(weights.sum(), 1.0)
        # Newest paper should have highest weight
        assert weights[0] > weights[1] > weights[2] > weights[3]

    def test_date_based_ignores_corpus_order(self):
        # Old paper first, new paper last — weights should still favor newest
        metadata = [
            {"date": "2020.01"},  # old, index 0
            {"date": "2026.03"},  # new, index 1
        ]
        weights = compute_time_decay_weights(2, metadata=metadata)
        assert weights[1] > weights[0], "Newer paper should have higher weight"

    def test_date_based_fallback_on_missing_dates(self):
        # Less than 50% have dates — should fall back to index-based
        metadata = [{"date": "2026.03"}, {}, {}, {}, {}]
        weights = compute_time_decay_weights(5, metadata=metadata)
        # Fallback: index-based, so index 0 has highest weight
        assert weights[0] > weights[-1]
        expected_raw = 1.0 / (1.0 + np.log10(np.arange(5) + 1))
        expected = expected_raw / expected_raw.sum()
        np.testing.assert_array_almost_equal(weights, expected)

    def test_date_based_handles_invalid_date_strings(self):
        metadata = [
            {"date": "2026.03"},
            {"date": "Asia"},  # invalid
            {"date": "2025.01"},
        ]
        weights = compute_time_decay_weights(3, metadata=metadata)
        assert len(weights) == 3
        assert np.isclose(weights.sum(), 1.0)
        # "Asia" gets median age, newest still highest
        assert weights[0] > weights[2]


class TestSimilarityScores:
    def test_identical_vectors(self):
        embeddings = np.array([[1.0, 0.0], [0.0, 1.0]])
        candidates = np.array([[1.0, 0.0]])
        scores = compute_similarity_scores(candidates, embeddings)
        assert scores.shape == (1, 2)
        assert np.isclose(scores[0, 0], 1.0)
        assert np.isclose(scores[0, 1], 0.0)

    def test_shape(self):
        corpus = np.random.randn(10, 64)
        candidates = np.random.randn(5, 64)
        scores = compute_similarity_scores(candidates, corpus)
        assert scores.shape == (5, 10)


class TestSaveLoadEmbeddings:
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.npy"
            data = np.random.randn(5, 32).astype(np.float32)
            save_embeddings(data, path)
            loaded = load_embeddings(path)
            np.testing.assert_array_equal(data, loaded)

    def test_load_missing_returns_none(self):
        result = load_embeddings(Path("/nonexistent/path.npy"))
        assert result is None


class TestRankCandidates:
    def test_returns_sorted_by_score(self):
        corpus_embeddings = np.array(
            [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32
        )
        candidate_embeddings = np.array(
            [
                [1.0, 0.0, 0.0],  # similar to corpus[0]
                [0.0, 0.0, 1.0],  # dissimilar
                [0.5, 0.5, 0.0],  # moderate
            ],
            dtype=np.float32,
        )
        candidates = [
            {"title": "Close"},
            {"title": "Far"},
            {"title": "Middle"},
        ]
        ranked = rank_candidates(
            candidates, candidate_embeddings, corpus_embeddings, top_k=3
        )
        assert ranked[0]["title"] == "Close"
        assert all("_embedding_score" in r for r in ranked)

    def test_top_k_limits_output(self):
        corpus = np.random.randn(5, 16).astype(np.float32)
        cands = np.random.randn(10, 16).astype(np.float32)
        papers = [{"title": f"Paper {i}"} for i in range(10)]
        ranked = rank_candidates(papers, cands, corpus, top_k=3)
        assert len(ranked) == 3

    def test_empty_corpus_returns_all_with_zero_score(self):
        cands = np.random.randn(5, 16).astype(np.float32)
        papers = [{"title": f"Paper {i}"} for i in range(5)]
        ranked = rank_candidates(
            papers, cands, np.empty((0, 16), dtype=np.float32), top_k=3
        )
        assert len(ranked) == 3
        assert all(r["_embedding_score"] == 0.0 for r in ranked)


class TestLoadCorpus:
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_dir = Path(tmpdir)
            emb = np.random.randn(3, 8).astype(np.float32)
            meta = [{"title": f"P{i}"} for i in range(3)]
            np.save(corpus_dir / "corpus_embeddings.npy", emb)
            with open(corpus_dir / "corpus_metadata.json", "w") as f:
                json.dump(meta, f)
            loaded_emb, loaded_meta = load_corpus(corpus_dir)
            np.testing.assert_array_equal(loaded_emb, emb)
            assert len(loaded_meta) == 3

    def test_missing_returns_none_and_empty(self):
        emb, meta = load_corpus(Path("/nonexistent"))
        assert emb is None
        assert meta == []
