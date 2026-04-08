import pytest
import numpy as np
from pathlib import Path
from unittest.mock import patch, MagicMock
import yaml
from scripts.feedback import on_collect_paper, update_taste_stats, add_paper_to_corpus


def _make_paper():
    return {
        "title": "New Robot Paper",
        "abstract": "A novel approach to manipulation.",
        "authors": ["Alice"],
        "arxiv_id": "2604.99999",
        "category": "Manipulation",
        "date": "2026.04",
    }


def _write_profile(path, total=510):
    profile = {
        "preferences": {"like": [], "dislike": []},
        "hard_rules": {"positive_keywords": [], "negative_keywords": [], "author_boost": []},
        "stats": {
            "total_collected": total,
            "top_categories": [{"category": "Manipulation", "count": 57}],
            "last_updated": "2026-04-07",
        },
    }
    path.write_text(yaml.dump(profile, allow_unicode=True))
    return profile


def test_update_taste_stats_increments_total(tmp_path):
    profile_path = tmp_path / "taste_profile.yaml"
    _write_profile(profile_path, total=100)
    updated = update_taste_stats(_make_paper(), profile_path)
    assert updated["stats"]["total_collected"] == 101

def test_update_taste_stats_updates_category_count(tmp_path):
    profile_path = tmp_path / "taste_profile.yaml"
    _write_profile(profile_path)
    updated = update_taste_stats(_make_paper(), profile_path)
    manip = [c for c in updated["stats"]["top_categories"] if c["category"] == "Manipulation"]
    assert manip[0]["count"] == 58

def test_update_taste_stats_adds_new_category(tmp_path):
    profile_path = tmp_path / "taste_profile.yaml"
    _write_profile(profile_path)
    paper = _make_paper()
    paper["category"] = "Navigation"
    updated = update_taste_stats(paper, profile_path)
    nav = [c for c in updated["stats"]["top_categories"] if c["category"] == "Navigation"]
    assert len(nav) == 1
    assert nav[0]["count"] == 1

@patch("scripts.feedback.append_to_corpus")
def test_add_paper_to_corpus_calls_append(mock_append, tmp_path):
    add_paper_to_corpus(_make_paper(), tmp_path)
    mock_append.assert_called_once()

@patch("scripts.feedback.add_paper_to_corpus")
@patch("scripts.feedback.update_taste_stats")
def test_on_collect_paper_full_flow(mock_stats, mock_embed, tmp_path):
    mock_stats.return_value = {"stats": {"total_collected": 511}}
    result = on_collect_paper(
        _make_paper(),
        corpus_dir=tmp_path,
        compile_wiki=False,
    )
    assert result["profile_updated"] is True
    assert result["embedding_added"] is True
    assert result["wiki_compiled"] is False
