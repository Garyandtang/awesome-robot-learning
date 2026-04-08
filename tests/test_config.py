import pytest
from pathlib import Path
from scripts.config import (
    load_config,
    load_categories,
    load_active_topics,
    load_taste_profile,
    save_taste_profile,
    load_embedding_config,
    get_wiki_path,
)


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


def test_load_taste_profile(tmp_path):
    profile_path = tmp_path / "taste_profile.yaml"
    profile_path.write_text("preferences:\n  like: []\nstats:\n  total_collected: 10\n")
    profile = load_taste_profile(profile_path)
    assert profile["stats"]["total_collected"] == 10


def test_save_taste_profile_atomic(tmp_path):
    profile_path = tmp_path / "taste_profile.yaml"
    profile = {"preferences": {"like": []}, "stats": {"total_collected": 5}}
    save_taste_profile(profile, profile_path)
    loaded = load_taste_profile(profile_path)
    assert loaded["stats"]["total_collected"] == 5


def test_load_embedding_config_defaults():
    config = load_embedding_config()
    assert config["model_name"] == "jinaai/jina-embeddings-v5-text-nano"
    assert config["dim"] == 768
    assert config["top_k"] == 30


def test_load_embedding_config_from_profile(tmp_path):
    profile_path = tmp_path / "taste_profile.yaml"
    profile_path.write_text(
        "embedding:\n"
        "  model_name: custom-model\n"
        "  dim: 512\n"
        "  top_k: 20\n"
    )
    config = load_embedding_config(profile_path)
    assert config["model_name"] == "custom-model"
    assert config["dim"] == 512
    assert config["top_k"] == 20


def test_load_embedding_config_partial_override(tmp_path):
    profile_path = tmp_path / "taste_profile.yaml"
    profile_path.write_text("embedding:\n  top_k: 50\n")
    config = load_embedding_config(profile_path)
    assert config["model_name"] == "jinaai/jina-embeddings-v5-text-nano"
    assert config["dim"] == 768
    assert config["top_k"] == 50


def test_get_wiki_path(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"awesome_repo:\n  path: '{tmp_path}'\n")
    monkeypatch.setattr("scripts.config.DEFAULT_CONFIG_PATH", config_file)
    path = get_wiki_path()
    assert path.name == "wiki"
    assert path == tmp_path / "wiki"
