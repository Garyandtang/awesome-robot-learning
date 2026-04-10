"""Build wiki index files: INDEX.md, papers/INDEX.md, concepts/INDEX.md, TOPIC-MAP.md."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import yaml

from scripts.config import get_wiki_path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared utility
# ---------------------------------------------------------------------------


def parse_frontmatter(content: str) -> dict | None:
    """Parse full YAML frontmatter from a Markdown file.

    Returns the parsed dict, or None if no frontmatter found.
    """
    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        return None
    try:
        result = yaml.safe_load(fm_match.group(1))
        return result if isinstance(result, dict) else None
    except yaml.YAMLError:
        return None


# ---------------------------------------------------------------------------
# Paper Index
# ---------------------------------------------------------------------------


def build_paper_index(wiki_dir: Path | None = None) -> Path:
    """Build papers/INDEX.md: all papers grouped by year with one-line summaries.

    Returns path to the written file.
    """
    resolved = wiki_dir if wiki_dir is not None else get_wiki_path()
    papers_dir = resolved / "papers"
    if not papers_dir.is_dir():
        papers_dir.mkdir(parents=True, exist_ok=True)

    # Scan all paper pages
    papers_by_year: dict[str, list[dict]] = defaultdict(list)
    for md_file in sorted(papers_dir.glob("*.md")):
        if md_file.name == "INDEX.md":
            continue
        content = md_file.read_text(encoding="utf-8")
        fm = parse_frontmatter(content)
        if fm is None:
            fm = {}

        date_str = fm.get("date", "")
        year = date_str.split(".")[0] if "." in str(date_str) else str(date_str)[:4]
        if not year or not year.isdigit():
            year = "Unknown"

        # Extract concept names from frontmatter
        concepts_list = fm.get("concepts", [])
        concept_names = []
        for c in concepts_list:
            if isinstance(c, dict):
                concept_names.append(c.get("name", ""))
            elif isinstance(c, str):
                concept_names.append(c)

        papers_by_year[year].append({
            "id": fm.get("arxiv_id", md_file.stem),
            "title": fm.get("title", md_file.stem),
            "date": str(date_str),
            "summary": fm.get("summary", ""),
            "concepts": concept_names,
            "filename": md_file.name,
        })

    # Build markdown
    total = sum(len(ps) for ps in papers_by_year.values())
    lines = [
        "# Paper Index",
        "",
        f"> {total} papers, sorted by date descending",
        "",
    ]

    for year in sorted(papers_by_year.keys(), reverse=True):
        papers = papers_by_year[year]
        lines.append(f"## {year}")
        lines.append("")
        lines.append("| ID | Title | Date | Summary | Concepts |")
        lines.append("|----|-------|------|---------|----------|")
        for p in sorted(papers, key=lambda x: x["date"], reverse=True):
            concepts_str = ", ".join(f"[[{c}]]" for c in p["concepts"][:5]) if p["concepts"] else ""
            summary = p["summary"][:80] if p["summary"] else ""
            lines.append(
                f"| [[{p['id']}]] | {p['title'][:60]} | {p['date']} | {summary} | {concepts_str} |"
            )
        lines.append("")

    output = papers_dir / "INDEX.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Built paper index: %d papers", total)
    return output


# ---------------------------------------------------------------------------
# Concept Index
# ---------------------------------------------------------------------------


def build_concept_index(wiki_dir: Path | None = None) -> Path:
    """Build concepts/INDEX.md: all concepts sorted alphabetically.

    Returns path to the written file.
    """
    resolved = wiki_dir if wiki_dir is not None else get_wiki_path()
    concepts_dir = resolved / "concepts"
    if not concepts_dir.is_dir():
        concepts_dir.mkdir(parents=True, exist_ok=True)

    concepts: list[dict] = []
    for md_file in sorted(concepts_dir.glob("*.md")):
        if md_file.name == "INDEX.md":
            continue
        content = md_file.read_text(encoding="utf-8")
        fm = parse_frontmatter(content)
        if fm is None:
            fm = {}

        name = fm.get("concept", md_file.stem.replace("-", " ").title())
        papers = fm.get("papers", [])
        description = fm.get("description", "")

        concepts.append({
            "name": name,
            "papers_count": len(papers) if isinstance(papers, list) else 0,
            "description": description,
        })

    # Sort alphabetically
    concepts.sort(key=lambda c: c["name"].lower())

    lines = [
        "# Concept Index",
        "",
        f"> {len(concepts)} concepts, sorted alphabetically",
        "",
        "| Concept | Papers | Description |",
        "|---------|--------|-------------|",
    ]
    for c in concepts:
        lines.append(f"| [[{c['name']}]] | {c['papers_count']} | {c['description']} |")
    lines.append("")

    output = concepts_dir / "INDEX.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Built concept index: %d concepts", len(concepts))
    return output


# ---------------------------------------------------------------------------
# Global Index
# ---------------------------------------------------------------------------


def build_global_index(wiki_dir: Path | None = None) -> Path:
    """Build INDEX.md: global entry point with stats, recent, and health.

    Returns path to the written file.
    """
    resolved = wiki_dir if wiki_dir is not None else get_wiki_path()

    # Count papers and concepts
    papers_dir = resolved / "papers"
    concepts_dir = resolved / "concepts"

    paper_count = 0
    if papers_dir.is_dir():
        paper_count = len([f for f in papers_dir.glob("*.md") if f.name != "INDEX.md"])
    concept_count = 0
    if concepts_dir.is_dir():
        concept_count = len([f for f in concepts_dir.glob("*.md") if f.name != "INDEX.md"])

    # Find recent papers (last 7 days).
    # Note: YAML auto-parses ISO dates into datetime.date, so normalize any
    # value we read from frontmatter back to an ISO string before comparing.
    recent_cutoff = (date.today() - timedelta(days=7)).isoformat()

    def _compiled_str(value) -> str:
        if isinstance(value, (date,)):
            return value.isoformat()
        return str(value) if value is not None else ""

    recent_papers: list[dict] = []
    if papers_dir.is_dir():
        for md_file in papers_dir.glob("*.md"):
            if md_file.name == "INDEX.md":
                continue
            content = md_file.read_text(encoding="utf-8")
            fm = parse_frontmatter(content)
            if not fm:
                continue
            compiled_str = _compiled_str(fm.get("compiled"))
            if compiled_str >= recent_cutoff:
                concepts_list = fm.get("concepts", [])
                concept_names = []
                for c in concepts_list:
                    if isinstance(c, dict):
                        concept_names.append(c.get("name", ""))
                    elif isinstance(c, str):
                        concept_names.append(c)
                recent_papers.append({
                    "id": fm.get("arxiv_id", md_file.stem),
                    "title": fm.get("title", md_file.stem),
                    "compiled": compiled_str,
                    "concepts": concept_names,
                })

    recent_papers.sort(key=lambda p: p["compiled"], reverse=True)

    # Count stale raw items
    stale_count = 0
    raw_dir = resolved / "raw" / "papers"
    if raw_dir.is_dir():
        for meta_file in raw_dir.glob("*/meta.yaml"):
            try:
                meta = yaml.safe_load(meta_file.read_text(encoding="utf-8"))
                if meta and meta.get("compile_status", {}).get("stale", False):
                    stale_count += 1
            except Exception:
                pass

    # Count orphan papers (no concept links)
    orphan_count = 0
    if papers_dir.is_dir():
        for md_file in papers_dir.glob("*.md"):
            if md_file.name == "INDEX.md":
                continue
            content = md_file.read_text(encoding="utf-8")
            if not re.search(r"\[\[.+?\]\]", content):
                orphan_count += 1

    today = date.today().isoformat()
    topic_count = 0
    topic_map_path = resolved / "TOPIC-MAP.md"
    if topic_map_path.exists():
        topic_content = topic_map_path.read_text(encoding="utf-8")
        topic_count = len(re.findall(r"^## ", topic_content, re.MULTILINE))

    lines = [
        "# Robot Learning Research Wiki",
        "",
        f"> Last updated: {today} | {paper_count} papers \u00b7 {concept_count} concepts \u00b7 {topic_count} topics",
        "",
        "## Navigation",
        "",
        "| Resource | Description |",
        "|----------|-------------|",
        "| [Paper Index](papers/INDEX.md) | All papers with one-line summaries, grouped by year |",
        "| [Concept Index](concepts/INDEX.md) | All concepts with descriptions, sorted alphabetically |",
        "| [Topic Map](TOPIC-MAP.md) | Research topic hierarchy and concept relationships |",
        "",
    ]

    # Recent papers
    if recent_papers:
        lines.append("## Recent (last 7 days)")
        lines.append("")
        lines.append("| Date | Paper | Concepts |")
        lines.append("|------|-------|----------|")
        for p in recent_papers[:10]:
            concepts_str = ", ".join(f"[[{c}]]" for c in p["concepts"][:3])
            lines.append(f"| {p['compiled']} | [[{p['id']}]] {p['title'][:50]} | {concepts_str} |")
        lines.append("")

    # Wiki Health
    lines.append("## Wiki Health")
    lines.append("")
    lines.append(f"- Stale papers (raw updated, wiki not re-compiled): {stale_count}")
    lines.append(f"- Orphan papers (no concept links): {orphan_count}")
    lines.append("")

    output = resolved / "INDEX.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Built global index: %d papers, %d concepts", paper_count, concept_count)
    return output


# ---------------------------------------------------------------------------
# Topic Map Scaffold
# ---------------------------------------------------------------------------


def build_topic_map_scaffold(wiki_dir: Path | None = None) -> Path | None:
    """Create initial TOPIC-MAP.md from concept parent_topic fields.

    Does NOT overwrite if TOPIC-MAP.md already exists (LLM-maintained).
    Returns path if created, None if already exists.
    """
    resolved = wiki_dir if wiki_dir is not None else get_wiki_path()
    topic_map_path = resolved / "TOPIC-MAP.md"

    if topic_map_path.exists():
        logger.info("TOPIC-MAP.md already exists, skipping scaffold")
        return None

    # Collect parent_topic from concept pages
    concepts_dir = resolved / "concepts"
    topics: dict[str, list[str]] = defaultdict(list)

    if concepts_dir.is_dir():
        for md_file in concepts_dir.glob("*.md"):
            if md_file.name == "INDEX.md":
                continue
            content = md_file.read_text(encoding="utf-8")
            fm = parse_frontmatter(content)
            if fm:
                parent = fm.get("parent_topic", "Uncategorized")
                name = fm.get("concept", md_file.stem.replace("-", " ").title())
                topics[parent].append(name)

    # Also check new_concepts suggested_topic from paper frontmatter
    papers_dir = resolved / "papers"
    if papers_dir.is_dir():
        for md_file in papers_dir.glob("*.md"):
            if md_file.name == "INDEX.md":
                continue
            content = md_file.read_text(encoding="utf-8")
            fm = parse_frontmatter(content)
            if fm:
                for nc in fm.get("new_concepts", []):
                    if isinstance(nc, dict):
                        topic = nc.get("suggested_topic", "Uncategorized")
                        # Parse "Parent > Child" format
                        parts = topic.split(">")
                        parent = parts[0].strip() if parts else "Uncategorized"
                        name = nc.get("name", "")
                        if name and name not in topics.get(parent, []):
                            topics[parent].append(name)

    if not topics:
        # Create minimal scaffold
        topics["Uncategorized"] = []

    lines = [
        "# Topic Map",
        "",
        "> Research topic hierarchy. This file is primarily maintained by LLM lint.",
        "",
    ]

    for topic in sorted(topics.keys()):
        lines.append(f"## {topic}")
        for concept in sorted(topics[topic]):
            lines.append(f"- [[{concept}]]")
        lines.append("")

    topic_map_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Built topic map scaffold: %d topics", len(topics))
    return topic_map_path


# ---------------------------------------------------------------------------
# Build All
# ---------------------------------------------------------------------------


def build_all_indexes(wiki_dir: Path | None = None) -> dict:
    """Build all four index files.

    Returns {paper_index, concept_index, global_index, topic_map}.
    """
    resolved = wiki_dir if wiki_dir is not None else get_wiki_path()

    paper_index = build_paper_index(resolved)
    concept_index = build_concept_index(resolved)
    topic_map = build_topic_map_scaffold(resolved)
    global_index = build_global_index(resolved)  # Must be last (reads other indexes)

    return {
        "paper_index": paper_index,
        "concept_index": concept_index,
        "global_index": global_index,
        "topic_map": topic_map,
    }
