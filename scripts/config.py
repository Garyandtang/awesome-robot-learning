"""Load configuration from YAML files."""

from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "paper-collector" / "config.yaml"


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict:
    """Load the main credential/path config."""
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
