"""Tests for scripts/bootstrap_embeddings.py."""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from scripts.bootstrap_embeddings import enrich_with_abstracts, run_bootstrap


def _make_papers(n=5):
    return [
        {
            "title": f"Paper {i}",
            "abstract": "",
            "arxiv_id": f"2604.{i:05d}",
            "url": f"https://arxiv.org/abs/2604.{i:05d}",
        }
        for i in range(n)
    ]


@patch("scripts.bootstrap_embeddings.fetch_arxiv_metadata")
def test_enrich_with_abstracts_fills_abstracts(mock_fetch):
    mock_fetch.return_value = {"abstract": "Test abstract"}
    papers = _make_papers(3)
    enriched = enrich_with_abstracts(papers, batch_size=10, delay=0)
    assert all(p["abstract"] == "Test abstract" for p in enriched)
    assert mock_fetch.call_count == 3


@patch("scripts.bootstrap_embeddings.fetch_arxiv_metadata")
def test_enrich_with_abstracts_handles_failure(mock_fetch):
    mock_fetch.side_effect = Exception("API error")
    papers = _make_papers(2)
    enriched = enrich_with_abstracts(papers, batch_size=10, delay=0)
    assert len(enriched) == 2  # Papers still returned even if fetch fails


@patch("scripts.bootstrap_embeddings.fetch_arxiv_metadata")
def test_enrich_skips_papers_without_arxiv_id(mock_fetch):
    papers = [{"title": "No ID Paper", "abstract": "", "url": "https://example.com"}]
    enriched = enrich_with_abstracts(papers, batch_size=10, delay=0)
    assert len(enriched) == 1
    mock_fetch.assert_not_called()


@patch("scripts.bootstrap_embeddings.bootstrap_corpus")
@patch("scripts.bootstrap_embeddings.parse_awesome_list_entries")
def test_run_bootstrap_calls_pipeline(mock_parse, mock_bootstrap, tmp_path):
    mock_parse.return_value = _make_papers(3)
    import numpy as np

    mock_bootstrap.return_value = (np.zeros((3, 768)), _make_papers(3))

    readme = tmp_path / "README.md"
    readme.write_text("# Papers\n- [arXiv 2026.04](url), Paper 0\n")

    result = run_bootstrap(readme, tmp_path / "embeddings", fetch_abstracts=False)
    assert result["total_papers"] == 3
    mock_bootstrap.assert_called_once()


@patch("scripts.bootstrap_embeddings.fetch_arxiv_metadata")
def test_enrich_does_not_mutate_original(mock_fetch):
    """Verify immutability: original papers list is not modified."""
    mock_fetch.return_value = {"abstract": "New abstract"}
    papers = _make_papers(2)
    original_abstracts = [p["abstract"] for p in papers]
    enriched = enrich_with_abstracts(papers, batch_size=10, delay=0)
    # Original papers should be unchanged
    assert all(p["abstract"] == "" for p in papers)
    # Enriched papers should have new abstracts
    assert all(p["abstract"] == "New abstract" for p in enriched)


@patch("scripts.bootstrap_embeddings.fetch_arxiv_metadata")
def test_enrich_batches_with_delay(mock_fetch):
    """Verify batching: papers are processed in batches."""
    mock_fetch.return_value = {"abstract": "Abs"}
    papers = _make_papers(5)
    enriched = enrich_with_abstracts(papers, batch_size=2, delay=0)
    assert len(enriched) == 5
    assert mock_fetch.call_count == 5


@patch("scripts.bootstrap_embeddings.bootstrap_corpus")
@patch("scripts.bootstrap_embeddings.parse_awesome_list_entries")
def test_run_bootstrap_result_keys(mock_parse, mock_bootstrap, tmp_path):
    """Verify run_bootstrap returns expected keys."""
    mock_parse.return_value = _make_papers(5)
    import numpy as np

    mock_bootstrap.return_value = (np.zeros((5, 768)), _make_papers(5))

    readme = tmp_path / "README.md"
    readme.write_text("# Papers\n")

    result = run_bootstrap(readme, tmp_path / "embeddings", fetch_abstracts=False)
    assert "total_papers" in result
    assert "papers_with_abstracts" in result
    assert "corpus_size" in result
