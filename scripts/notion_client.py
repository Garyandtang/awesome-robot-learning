"""Write paper entries to a Notion database via the Notion API."""

from notion_client import Client

from scripts.config import load_config


def get_notion_client(config: dict | None = None) -> Client:
    """Create a Notion API client."""
    if config is None:
        config = load_config()
    return Client(auth=config["notion"]["token"])


def get_database_id(config: dict | None = None) -> str:
    """Get the target database ID from config."""
    if config is None:
        config = load_config()
    return config["notion"]["database_id"]


def add_paper(
    paper: dict,
    category: str,
    topics: list[str],
    relevance: str,
    method_summary: str,
    config: dict | None = None,
) -> str:
    """Add a paper to the Notion database.

    Returns the created page ID.
    """
    client = get_notion_client(config)
    db_id = get_database_id(config)
    # Build date in ISO format for Notion (YYYY-MM or YYYY-MM-DD)
    date_str = paper.get("date", "")
    notion_date = None
    if date_str:
        parts = date_str.replace(".", "-").split("-")
        if len(parts) >= 2:
            notion_date = {"start": f"{parts[0]}-{parts[1]}-01"}
    properties = {
        "Title": {"title": [{"text": {"content": paper["title"]}}]},
        "Category": {"select": {"name": category}},
        "Topics": {"multi_select": [{"name": t} for t in topics]},
        "Venue": {"select": {"name": paper.get("venue", "arXiv")}},
        "Relevance": {"select": {"name": relevance}},
        "Method Summary": {"rich_text": [{"text": {"content": method_summary[:2000]}}]} if method_summary else {"rich_text": []},
        "URL": {"url": paper.get("url", "")},
        "Has Code": {"checkbox": paper.get("has_code", False)},
    }
    if notion_date:
        properties["Date"] = {"date": notion_date}
    if paper.get("project_url"):
        properties["Project URL"] = {"url": paper["project_url"]}
    # Method Summary also goes into the page body as a paragraph block for longer content
    children = []
    if method_summary:
        children.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"text": {"content": method_summary}}]
            },
        })
    resp = client.pages.create(
        parent={"database_id": db_id},
        properties=properties,
        children=children,
    )
    return resp["id"]
