"""Tests for feedback.py — corpus update, taste stats, wiki compilation."""

import json
import numpy as np
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from scripts.feedback import update_corpus, update_taste_stats, run_feedback
from scripts.taste_engine import ScoredPaper


def _make_scored(
    title: str, relevance: str, abstract: str = "test abstract"
) -> ScoredPaper:
    paper = {
        "title": title,
        "url": f"https://arxiv.org/abs/2604.0000{title[-1]}",
        "arxiv_id": f"2604.0000{title[-1]}",
        "authors": ["Alice"],
        "abstract": abstract,
    }
    return ScoredPaper(
        paper=paper,
        relevance=relevance,
        reason="测试理由",
        embedding_score=0.5,
        source_level="llm",
    )


class TestUpdateCorpus:
    def test_adds_high_papers(self, tmp_path):
        metadata_path = tmp_path / "corpus_metadata.json"
        metadata_path.write_text(json.dumps([{"title": "Old Paper"}]))

        scored = [
            _make_scored("Paper A", "High"),
            _make_scored("Paper B", "Medium"),
            _make_scored("Paper C", "Low"),
        ]

        with patch("scripts.feedback.append_to_corpus") as mock_append:
            added = update_corpus(scored, tmp_path, relevance_threshold="High")

        assert added == 1
        mock_append.assert_called_once()
        texts = mock_append.call_args[0][0]
        assert len(texts) == 1
        assert "Paper A" in texts[0]

    def test_adds_high_and_medium_when_threshold_medium(self, tmp_path):
        metadata_path = tmp_path / "corpus_metadata.json"
        metadata_path.write_text(json.dumps([]))

        scored = [
            _make_scored("Paper A", "High"),
            _make_scored("Paper B", "Medium"),
            _make_scored("Paper C", "Low"),
        ]

        with patch("scripts.feedback.append_to_corpus") as mock_append:
            added = update_corpus(scored, tmp_path, relevance_threshold="Medium")

        assert added == 2

    def test_skips_duplicates(self, tmp_path):
        metadata_path = tmp_path / "corpus_metadata.json"
        metadata_path.write_text(json.dumps([{"title": "Paper A"}]))

        scored = [_make_scored("Paper A", "High")]

        with patch("scripts.feedback.append_to_corpus") as mock_append:
            added = update_corpus(scored, tmp_path)

        assert added == 0
        mock_append.assert_not_called()

    def test_returns_zero_when_no_papers_above_threshold(self, tmp_path):
        scored = [_make_scored("Paper C", "Low")]
        added = update_corpus(scored, tmp_path)
        assert added == 0


class TestUpdateTasteStats:
    def test_appends_daily_history(self):
        scored = [
            _make_scored("Paper A", "High"),
            _make_scored("Paper B", "Medium"),
            _make_scored("Paper C", "Low"),
        ]

        with patch("scripts.feedback.load_taste_profile") as mock_load, \
             patch("scripts.feedback.save_taste_profile") as mock_save:
            mock_load.return_value = {
                "stats": {"last_updated": "2026-04-07"},
            }
            update_taste_stats(scored)

        mock_save.assert_called_once()
        saved = mock_save.call_args[0][0]
        history = saved["stats"]["daily_history"]
        assert len(history) == 1
        assert history[0]["high"] == 1
        assert history[0]["medium"] == 1
        assert history[0]["low"] == 1
        assert history[0]["scored"] == 3

    def test_keeps_max_90_days(self):
        existing = [
            {"date": f"2026-01-{i:02d}", "scored": 5, "high": 1, "medium": 2, "low": 2}
            for i in range(1, 91)
        ]

        with patch("scripts.feedback.load_taste_profile") as mock_load, \
             patch("scripts.feedback.save_taste_profile") as mock_save:
            mock_load.return_value = {"stats": {"daily_history": existing}}
            update_taste_stats([_make_scored("Paper A", "High")])

        saved = mock_save.call_args[0][0]
        assert len(saved["stats"]["daily_history"]) == 90


class TestRunFeedback:
    @patch("scripts.feedback.compile_wiki_for_scored", return_value=1)
    @patch("scripts.feedback.update_taste_stats")
    @patch("scripts.feedback.update_corpus", return_value=2)
    def test_runs_all_steps(self, mock_corpus, mock_stats, mock_wiki, tmp_path):
        scored = [_make_scored("Paper A", "High")]
        result = run_feedback(scored, tmp_path)

        assert result["papers_added_to_corpus"] == 2
        assert result["stats_updated"] is True
        assert result["wiki_compiled"] == 1

    @patch("scripts.feedback.compile_wiki_for_scored")
    @patch("scripts.feedback.update_taste_stats")
    @patch("scripts.feedback.update_corpus", return_value=0)
    def test_skips_wiki_when_disabled(self, mock_corpus, mock_stats, mock_wiki, tmp_path):
        scored = [_make_scored("Paper A", "High")]
        result = run_feedback(scored, tmp_path, compile_wiki=False)

        mock_wiki.assert_not_called()
        assert result["wiki_compiled"] == 0

    @patch("scripts.feedback.compile_wiki_for_scored", side_effect=Exception("boom"))
    @patch("scripts.feedback.update_taste_stats")
    @patch("scripts.feedback.update_corpus", return_value=1)
    def test_continues_on_wiki_failure(self, mock_corpus, mock_stats, mock_wiki, tmp_path):
        scored = [_make_scored("Paper A", "High")]
        result = run_feedback(scored, tmp_path)

        assert result["papers_added_to_corpus"] == 1
        assert result["stats_updated"] is True
        assert result["wiki_compiled"] == 0
