import pytest
from scripts.search_papers import build_arxiv_query, build_s2_query, deduplicate


def test_build_arxiv_query_broad():
    query = build_arxiv_query(categories=["cs.RO", "cs.AI"])
    assert "cat:cs.RO" in query
    assert "cat:cs.AI" in query
    assert " OR " in query


def test_build_arxiv_query_with_keywords():
    query = build_arxiv_query(
        categories=["cs.RO"],
        keywords=["vision language action", "VLA"],
    )
    assert "cat:cs.RO" in query
    assert "vision language action" in query


def test_build_s2_query():
    query = build_s2_query(keywords=["force control", "tactile"])
    assert "force control" in query
    assert "tactile" in query


def test_deduplicate():
    papers = [
        {"arxiv_id": "2604.001", "title": "A"},
        {"arxiv_id": "2604.002", "title": "B"},
        {"arxiv_id": "2604.001", "title": "A duplicate"},
    ]
    seen = {"2604.999": {"date_seen": "2026-04-01", "relevance": "high"}}
    result = deduplicate(papers, seen)
    assert len(result) == 2
    assert all(p["arxiv_id"] != "2604.999" for p in result)


def test_deduplicate_filters_seen():
    papers = [
        {"arxiv_id": "2604.001", "title": "A"},
        {"arxiv_id": "2604.002", "title": "B"},
    ]
    seen = {"2604.001": {"date_seen": "2026-04-01", "relevance": "high"}}
    result = deduplicate(papers, seen)
    assert len(result) == 1
    assert result[0]["arxiv_id"] == "2604.002"
