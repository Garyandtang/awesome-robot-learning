import pytest
from pathlib import Path
from scripts.config import load_config, load_categories, load_active_topics


def test_load_config(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "zotero:\n"
        "  user_id: '12345'\n"
        "  api_key: 'abc'\n"
        "notion:\n"
        "  token: 'ntn_xxx'\n"
        "  database_id: 'db123'\n"
        "feishu:\n"
        "  chat_id: 'oc_xxx'\n"
        "awesome_repo:\n"
        "  path: '/tmp/repo'\n"
        "research_idea:\n"
        "  path: '/tmp/research'\n"
    )
    cfg = load_config(config_file)
    assert cfg["zotero"]["user_id"] == "12345"
    assert cfg["notion"]["token"] == "ntn_xxx"
    assert cfg["feishu"]["chat_id"] == "oc_xxx"


def test_load_categories(tmp_path):
    cat_file = tmp_path / "categories.yaml"
    cat_file.write_text(
        "categories:\n"
        "  - Manipulation\n"
        "  - VLA\n"
    )
    cats = load_categories(cat_file)
    assert cats == ["Manipulation", "VLA"]


def test_load_active_topics(tmp_path):
    research_dir = tmp_path / "research_idea"
    topic_dir = research_dir / "vla"
    topic_dir.mkdir(parents=True)
    (topic_dir / "topic.yaml").write_text(
        "name: 'VLA'\n"
        "description: 'test'\n"
        "category: 'VLA'\n"
        "keywords:\n"
        "  - 'vla'\n"
        "arxiv_categories:\n"
        "  - 'cs.RO'\n"
        "active: true\n"
    )
    inactive_dir = research_dir / "old"
    inactive_dir.mkdir()
    (inactive_dir / "topic.yaml").write_text(
        "name: 'Old'\n"
        "description: 'inactive'\n"
        "category: 'Other'\n"
        "keywords:\n"
        "  - 'old'\n"
        "arxiv_categories:\n"
        "  - 'cs.RO'\n"
        "active: false\n"
    )
    topics = load_active_topics(research_dir)
    assert len(topics) == 1
    assert topics[0]["name"] == "VLA"
