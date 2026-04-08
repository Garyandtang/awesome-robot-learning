"""Tests for scripts.source_discovery module."""

import pytest

from scripts.source_discovery import (
    extract_top_authors_from_corpus,
    generate_feed_candidates,
)


def test_extract_top_authors_counts_correctly():
    metadata = [
        {"authors": ["Alice", "Bob"], "arxiv_id": "1"},
        {"authors": ["Alice", "Charlie"], "arxiv_id": "2"},
        {"authors": ["Alice", "Bob", "Dave"], "arxiv_id": "3"},
    ]
    result = extract_top_authors_from_corpus(metadata, min_papers=2)
    assert result[0]["name"] == "Alice"
    assert result[0]["paper_count"] == 3
    assert len(result) == 2  # Alice (3), Bob (2)


def test_extract_top_authors_respects_min_papers():
    metadata = [{"authors": ["Alice"], "arxiv_id": "1"}]
    result = extract_top_authors_from_corpus(metadata, min_papers=2)
    assert len(result) == 0


def test_extract_top_authors_empty_corpus():
    result = extract_top_authors_from_corpus([], min_papers=1)
    assert result == []


def test_generate_feed_candidates_deduplicates():
    authors = [
        {"name": "Alice", "homepage_url": "https://alice.com", "paper_count": 5},
        {"name": "Bob", "homepage_url": "https://bob.com", "paper_count": 3},
    ]
    existing_feeds = [{"url": "https://alice.com/feed.xml", "name": "Alice"}]
    candidates = generate_feed_candidates(authors, existing_feeds)
    alice_candidates = [c for c in candidates if "alice" in c.get("name", "").lower()]
    assert len(alice_candidates) == 0


def test_generate_feed_candidates_keeps_new():
    authors = [
        {"name": "Bob", "homepage_url": "https://bob.com", "paper_count": 3},
    ]
    existing_feeds = [{"url": "https://alice.com/feed.xml", "name": "Alice"}]
    candidates = generate_feed_candidates(authors, existing_feeds)
    assert len(candidates) == 1
    assert candidates[0]["name"] == "Bob"


def test_generate_feed_candidates_skips_no_homepage():
    authors = [{"name": "Charlie", "paper_count": 2}]
    candidates = generate_feed_candidates(authors, [])
    assert len(candidates) == 0
