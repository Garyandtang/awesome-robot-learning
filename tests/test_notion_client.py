"""Tests for scripts/notion_client.py enhancements."""

import pytest
from unittest.mock import patch, MagicMock
from scripts.notion_client import add_paper


@patch("scripts.notion_client.get_notion_client")
@patch("scripts.notion_client.get_database_id", return_value="fake-db-id")
def test_add_paper_includes_recommendation_reason(mock_db, mock_client):
    mock_api = MagicMock()
    mock_api.pages.create.return_value = {"id": "page-123"}
    mock_client.return_value = mock_api

    paper = {
        "title": "Test Paper",
        "venue": "arXiv",
        "date": "2026.04",
        "url": "https://arxiv.org/abs/2604.00001",
        "has_code": False,
        "project_url": None,
    }

    add_paper(
        paper=paper,
        category="VLA",
        topics=["VLA for Manipulation"],
        relevance="High",
        method_summary="方法摘要",
        recommendation_reason="推荐理由：和你的研究方向相关",
    )

    call_args = mock_api.pages.create.call_args
    props = call_args[1]["properties"]
    assert "Recommendation Reason" in props
    assert props["Recommendation Reason"]["rich_text"][0]["text"]["content"] == "推荐理由：和你的研究方向相关"


@patch("scripts.notion_client.get_notion_client")
@patch("scripts.notion_client.get_database_id", return_value="fake-db-id")
def test_add_paper_includes_source_field(mock_db, mock_client):
    mock_api = MagicMock()
    mock_api.pages.create.return_value = {"id": "page-123"}
    mock_client.return_value = mock_api

    paper = {
        "title": "Test Paper",
        "venue": "blog",
        "date": "2026.04",
        "url": "https://example.com/post",
        "has_code": False,
        "project_url": None,
    }

    add_paper(
        paper=paper,
        category="VLA",
        topics=[],
        relevance="Medium",
        method_summary="摘要",
        source="RSS",
    )

    call_args = mock_api.pages.create.call_args
    props = call_args[1]["properties"]
    assert "Source" in props
    assert props["Source"]["select"]["name"] == "RSS"


@patch("scripts.notion_client.get_notion_client")
@patch("scripts.notion_client.get_database_id", return_value="fake-db-id")
def test_add_paper_backward_compatible(mock_db, mock_client):
    """Existing callers without new params still work."""
    mock_api = MagicMock()
    mock_api.pages.create.return_value = {"id": "page-123"}
    mock_client.return_value = mock_api

    paper = {
        "title": "Test Paper",
        "venue": "arXiv",
        "date": "2026.04",
        "url": "https://arxiv.org/abs/2604.00001",
        "has_code": False,
        "project_url": None,
    }

    # Call without new params — should not raise
    result = add_paper(
        paper=paper,
        category="VLA",
        topics=[],
        relevance="High",
        method_summary="摘要",
    )
    assert result == "page-123"
