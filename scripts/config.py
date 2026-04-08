"""Load configuration from YAML files."""

import tempfile
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "paper-collector" / "config.yaml"

_EMBEDDING_DEFAULTS: dict = {
    "model_name": "jinaai/jina-embeddings-v5-text-nano",
    "dim": 768,
    "top_k": 30,
    "corpus_min_for_ranking": 10,
}


def load_config(path: Path | None = None) -> dict:
    """Load the main credential/path config."""
    if path is None:
        path = DEFAULT_CONFIG_PATH
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_categories(path: Path | None = None) -> list[str]:
    """Load category list from categories.yaml."""
    if path is None:
        cfg = load_config()
        path = Path(cfg["research_idea"]["path"]) / "categories.yaml"
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["categories"]


def load_feeds(feeds_path: Path | None = None) -> list[dict]:
    """Load RSS feed subscriptions from feeds.yaml."""
    if feeds_path is None:
        cfg = load_config()
        feeds_path = Path(cfg["awesome_repo"]["path"]) / "feeds.yaml"
    if not feeds_path.exists():
        return []
    with open(feeds_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("feeds", [])


def load_taste_profile(path: Path | None = None) -> dict:
    """Load taste_profile.yaml from data/ directory."""
    if path is None:
        cfg = load_config()
        path = Path(cfg["awesome_repo"]["path"]) / "data" / "taste_profile.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_taste_profile(profile: dict, path: Path | None = None) -> None:
    """Save taste_profile.yaml atomically."""
    if path is None:
        cfg = load_config()
        path = Path(cfg["awesome_repo"]["path"]) / "data" / "taste_profile.yaml"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with open(tmp_fd, "w", encoding="utf-8") as f:
            yaml.dump(profile, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        Path(tmp_name).replace(path)
    except Exception:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def load_embedding_config(profile_path: Path | None = None) -> dict:
    """Return embedding model config with defaults, optionally overridden by taste_profile.yaml."""
    config = dict(_EMBEDDING_DEFAULTS)
    if profile_path is None:
        try:
            cfg = load_config()
            profile_path = Path(cfg["awesome_repo"]["path"]) / "data" / "taste_profile.yaml"
        except Exception:
            return config
    try:
        profile = load_taste_profile(profile_path)
        overrides = (profile or {}).get("embedding", {}) or {}
        config.update(overrides)
    except (FileNotFoundError, TypeError):
        pass
    return config


def get_wiki_path() -> Path:
    """Return the wiki directory path."""
    cfg = load_config()
    return Path(cfg["awesome_repo"]["path"]) / "wiki"


def load_active_topics(research_dir: Path | None = None) -> list[dict]:
    """Load all active topic configs from research_idea subdirectories."""
    if research_dir is None:
        cfg = load_config()
        research_dir = Path(cfg["research_idea"]["path"])
    topics = []
    for topic_file in sorted(research_dir.glob("*/topic.yaml")):
        with open(topic_file, encoding="utf-8") as f:
            topic = yaml.safe_load(f)
        if topic.get("active", True):
            topic["_dir"] = str(topic_file.parent)
            topics.append(topic)
    return topics
