import pytest
from unittest.mock import patch, MagicMock
from scripts.fetch_paper import (
    parse_arxiv_id,
    fetch_arxiv_metadata,
    fetch_s2_metadata,
    fetch_fulltext,
    fetch_fulltext_html,
    fetch_fulltext_pdf,
)


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


# ---------------------------------------------------------------------------
# Full text fetching tests
# ---------------------------------------------------------------------------


@patch("scripts.fetch_paper.trafilatura")
def test_fetch_fulltext_html_success(mock_traf):
    mock_traf.fetch_url.return_value = "<html>paper content</html>"
    mock_traf.extract.return_value = "A" * 1000
    result = fetch_fulltext_html("2401.00003")
    assert result is not None
    assert len(result) == 1000
    mock_traf.fetch_url.assert_called_once()


@patch("scripts.fetch_paper.trafilatura")
def test_fetch_fulltext_html_returns_none_on_short_text(mock_traf):
    mock_traf.fetch_url.return_value = "<html>short</html>"
    mock_traf.extract.return_value = "short"
    result = fetch_fulltext_html("2401.00003")
    assert result is None


@patch("scripts.fetch_paper.trafilatura")
def test_fetch_fulltext_html_returns_none_on_failure(mock_traf):
    mock_traf.fetch_url.return_value = None
    result = fetch_fulltext_html("9999.99999")
    assert result is None


def test_fetch_fulltext_returns_none_for_empty_id():
    result = fetch_fulltext("")
    assert result is None


@patch("scripts.fetch_paper.fetch_fulltext_pdf", return_value="PDF fallback text" + "x" * 500)
@patch("scripts.fetch_paper.fetch_fulltext_html", return_value=None)
def test_fetch_fulltext_falls_back_to_pdf(mock_html, mock_pdf):
    result = fetch_fulltext("2401.00003")
    assert result is not None
    mock_html.assert_called_once_with("2401.00003")
    mock_pdf.assert_called_once_with("2401.00003")


@patch("scripts.fetch_paper.fetch_fulltext_html", return_value="HTML content" + "x" * 500)
def test_fetch_fulltext_prefers_html(mock_html):
    result = fetch_fulltext("2401.00003")
    assert result is not None
    assert "HTML content" in result
