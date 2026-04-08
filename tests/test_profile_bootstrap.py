"""Tests for scripts/profile_bootstrap.py."""

import pytest
from scripts.profile_bootstrap import (
    parse_awesome_list_entries,
    extract_author_stats,
    build_initial_taste_profile,
)


SAMPLE_README = """# Awesome-Humanoid-Robot-Learning

## Loco-Manipulation and Whole-Body-Control
- 🌟[website 2026.03](https://example.com/latent), LATENT: Learning Athletic Humanoid Tennis Skills
- [arXiv 2026.03](https://arxiv.org/abs/2603.12263), Some Paper Title
- [arXiv 2026.02](https://arxiv.org/abs/2602.23843), Another Paper Title, [website](https://example.com)

## Manipulation
- [arXiv 2026.01](https://arxiv.org/abs/2601.12345), Manipulation Paper
- 🌟 [CoRL 2025](https://arxiv.org/abs/2510.00001), Open Source Manipulation

## Hardware Design
- [arXiv 2025.12](https://arxiv.org/abs/2512.99999), Cool Hardware Paper
"""


def test_parse_awesome_list_entries():
    entries = parse_awesome_list_entries(SAMPLE_README)
    assert len(entries) == 6


def test_parse_awesome_list_entries_extracts_fields():
    entries = parse_awesome_list_entries(SAMPLE_README)
    first = entries[0]
    assert first["title"] == "LATENT: Learning Athletic Humanoid Tennis Skills"
    assert first["url"] == "https://example.com/latent"
    assert first["has_code"] is True


def test_parse_awesome_list_entries_extracts_arxiv_id():
    entries = parse_awesome_list_entries(SAMPLE_README)
    second = entries[1]
    assert second["arxiv_id"] == "2603.12263"
    assert second["url"] == "https://arxiv.org/abs/2603.12263"


def test_parse_awesome_list_entries_with_project_url():
    entries = parse_awesome_list_entries(SAMPLE_README)
    third = entries[2]
    assert third["project_url"] == "https://example.com"


def test_parse_awesome_list_entries_extracts_category():
    entries = parse_awesome_list_entries(SAMPLE_README)
    assert entries[0]["category"] == "Loco-Manipulation and Whole-Body-Control"
    assert entries[3]["category"] == "Manipulation"
    assert entries[5]["category"] == "Hardware Design"


def test_extract_author_stats():
    papers = [
        {"authors": ["Alice", "Bob", "Charlie"]},
        {"authors": ["Alice", "Bob"]},
        {"authors": ["Alice", "Dave"]},
    ]
    stats = extract_author_stats(papers)
    assert stats["Alice"] == 3
    assert stats["Bob"] == 2
    assert stats["Charlie"] == 1
    assert stats["Dave"] == 1


def test_build_initial_taste_profile():
    papers = [
        {"title": "Diffusion Policy for Manipulation", "authors": ["Alice", "Bob"], "category": "Manipulation", "arxiv_id": "2601.00001"},
        {"title": "VLA for Loco-Manipulation", "authors": ["Alice"], "category": "Loco-Manipulation and Whole-Body-Control", "arxiv_id": "2601.00002"},
    ]
    profile = build_initial_taste_profile(papers)
    assert "preferences" in profile
    assert "authors_whitelist" in profile
    assert "stats" in profile
    assert profile["stats"]["total_collected"] == 2
    assert len(profile["stats"]["top_categories"]) > 0
