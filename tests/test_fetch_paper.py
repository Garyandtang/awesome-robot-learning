import pytest
from scripts.fetch_paper import parse_arxiv_id, fetch_arxiv_metadata, fetch_s2_metadata


def test_parse_arxiv_id_from_abs_url():
    assert parse_arxiv_id("https://arxiv.org/abs/2604.12345") == "2604.12345"


def test_parse_arxiv_id_from_pdf_url():
    assert parse_arxiv_id("https://arxiv.org/pdf/2604.12345") == "2604.12345"


def test_parse_arxiv_id_with_version():
    assert parse_arxiv_id("https://arxiv.org/abs/2604.12345v2") == "2604.12345"


def test_parse_arxiv_id_bare():
    assert parse_arxiv_id("2604.12345") == "2604.12345"


def test_parse_arxiv_id_invalid():
    assert parse_arxiv_id("https://example.com") is None


def test_fetch_arxiv_metadata_returns_dict():
    """Integration test — hits real arXiv API."""
    # Use a known paper: "Attention Is All You Need"
    result = fetch_arxiv_metadata("1706.03762")
    assert result is not None
    assert result["title"] is not None
    assert len(result["title"]) > 0
    assert result["arxiv_id"] == "1706.03762"
    assert result["url"] == "https://arxiv.org/abs/1706.03762"
    assert "pdf_url" in result
    assert "authors" in result
    assert "abstract" in result
    assert "date" in result
    assert "venue" in result


def test_fetch_arxiv_metadata_invalid_id():
    result = fetch_arxiv_metadata("0000.00000")
    assert result is None


def test_fetch_s2_metadata_from_arxiv_id():
    """Integration test — hits real Semantic Scholar API."""
    result = fetch_s2_metadata(arxiv_id="1706.03762")
    assert result is not None
    assert "title" in result
    assert result["arxiv_id"] == "1706.03762"
