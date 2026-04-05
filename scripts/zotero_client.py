"""Write paper entries to Zotero via Web API v3 using pyzotero."""

from pyzotero import zotero

from scripts.config import load_config


def get_zotero_client(config: dict | None = None) -> zotero.Zotero:
    """Create a Zotero API client."""
    if config is None:
        config = load_config()
    return zotero.Zotero(
        config["zotero"]["user_id"],
        "user",
        config["zotero"]["api_key"],
    )


def get_or_create_collection(zot: zotero.Zotero, name: str) -> str:
    """Get collection key by name, creating it if it doesn't exist."""
    collections = zot.collections()
    for c in collections:
        if c["data"]["name"] == name:
            return c["key"]
    resp = zot.create_collections([{"name": name}])
    return resp["successful"]["0"]["data"]["key"]


def add_paper(paper: dict, category: str, topics: list[str], config: dict | None = None) -> str:
    """Add a paper to Zotero in the given category collection.

    Returns the Zotero item key.
    """
    zot = get_zotero_client(config)
    collection_key = get_or_create_collection(zot, category)
    tags = [{"tag": category}] + [{"tag": t} for t in topics]
    item = {
        "itemType": "journalArticle",
        "title": paper["title"],
        "creators": [
            {"creatorType": "author", "name": name}
            for name in paper.get("authors", [])
        ],
        "abstractNote": paper.get("abstract", ""),
        "url": paper.get("url", ""),
        "date": paper.get("date", ""),
        "collections": [collection_key],
        "tags": tags,
    }
    resp = zot.create_items([item])
    return resp["successful"]["0"]["data"]["key"]
