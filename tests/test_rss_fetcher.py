"""Tests for scripts/rss_fetcher.py."""

import pytest
from unittest.mock import patch, MagicMock
from scripts.rss_fetcher import parse_feed_entries, normalize_rss_entry, fetch_all_feeds


SAMPLE_FEED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Test Blog</title>
  <entry>
    <title>New Robot Learning Paper</title>
    <link href="https://example.com/post-1" rel="alternate"/>
    <published>2026-04-05T10:00:00Z</published>
    <summary>A summary of the post about robot learning.</summary>
    <author><name>Dr. Test</name></author>
  </entry>
  <entry>
    <title>Old Post</title>
    <link href="https://example.com/post-2" rel="alternate"/>
    <published>2025-01-01T10:00:00Z</published>
    <summary>An old post.</summary>
    <author><name>Dr. Test</name></author>
  </entry>
</feed>"""


def test_parse_feed_entries_extracts_all_entries():
    entries = parse_feed_entries(SAMPLE_FEED_XML)
    assert len(entries) == 2
    assert entries[0]["title"] == "New Robot Learning Paper"
    assert entries[1]["title"] == "Old Post"


def test_parse_feed_entries_extracts_fields():
    entries = parse_feed_entries(SAMPLE_FEED_XML)
    entry = entries[0]
    assert entry["url"] == "https://example.com/post-1"
    assert entry["published"] == "2026-04-05T10:00:00Z"
    assert "summary" in entry


def test_parse_feed_entries_empty_feed():
    xml = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
    <title>Empty</title></feed>"""
    entries = parse_feed_entries(xml)
    assert entries == []


def test_normalize_rss_entry():
    raw = {
        "title": "New Robot Learning Paper",
        "url": "https://example.com/post-1",
        "published": "2026-04-05T10:00:00Z",
        "summary": "A summary of the post.",
        "author": "Dr. Test",
    }
    feed_config = {
        "name": "Test Blog",
        "tags": ["manipulation"],
    }
    result = normalize_rss_entry(raw, feed_config)
    assert result["title"] == "New Robot Learning Paper"
    assert result["source_type"] == "rss"
    assert result["source_name"] == "Test Blog"
    assert result["url"] == "https://example.com/post-1"
    assert result["date"] == "2026.04"
    assert result["venue"] == "blog"
    assert result["arxiv_id"] == ""
    assert result["has_code"] is False


def test_normalize_rss_entry_bad_date():
    raw = {
        "title": "No Date Post",
        "url": "https://example.com/post",
        "published": "",
        "summary": "",
        "author": "",
    }
    feed_config = {"name": "Blog", "tags": []}
    result = normalize_rss_entry(raw, feed_config)
    assert result["date"] == ""


@patch("scripts.rss_fetcher.requests.get")
def test_fetch_all_feeds_with_mock(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = SAMPLE_FEED_XML
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    feeds = [
        {"url": "https://example.com/feed.xml", "name": "Test Blog", "tags": ["manipulation"]},
    ]
    seen = {}
    results = fetch_all_feeds(feeds, seen, days_back=365)
    assert len(results) >= 1
    assert results[0]["source_type"] == "rss"
