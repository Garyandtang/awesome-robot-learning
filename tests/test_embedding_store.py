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
