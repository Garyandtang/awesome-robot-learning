"""Insert paper entries into the awesome-robot-learning README.md."""

import re
import subprocess
from pathlib import Path

# Map category names to their heading text in README
SECTION_HEADINGS = {
    "Manipulation": "## Manipulation",
    "Loco-Manipulation": "## Loco-Manipulation",
    "VLA": "## VLA (Vision-Language-Action)",
    "Force Control & Perception": "## Force Control & Perception",
    "Sim-to-Real": "## Sim-to-Real",
    "System & Foundation Model": "## System & Foundation Model",
    "Hardware": "## Hardware",
}

# Regex to extract date from an entry line: [venue YYYY.MM]
DATE_RE = re.compile(r"\[.+?\s(\d{4})\.(\d{2})\]")
# Regex to extract arXiv ID from entry line
ARXIV_RE = re.compile(r"arxiv\.org/abs/(\d{4}\.\d+)")


def format_entry(paper: dict) -> str:
    """Format a paper dict into an awesome-list entry line."""
    prefix = "🌟 " if paper.get("has_code") else ""
    line = f"- {prefix}[{paper['venue']} {paper['date']}]({paper['url']}), {paper['title']}"
    if paper.get("project_url"):
        line += f", [website]({paper['project_url']})"
    return line


def find_section_range(lines: list[str], category: str) -> tuple[int, int]:
    """Find the line range (start, end) for a section in the README.

    Returns (section_heading_line, next_section_heading_line).
    """
    heading = SECTION_HEADINGS.get(category, f"## {category}")
    start = None
    for i, line in enumerate(lines):
        if line.strip() == heading.strip() or line.strip().startswith(heading.strip()):
            start = i
        elif start is not None and line.startswith("## "):
            return start, i
    if start is not None:
        # Last section — find end of file or "---"
        for i in range(start + 1, len(lines)):
            if lines[i].strip() == "---":
                return start, i
        return start, len(lines)
    raise ValueError(f"Section '{category}' not found in README")


def _parse_entry_sort_key(line: str) -> tuple[int, int, int]:
    """Extract (year, month, arxiv_num) for sorting. Higher = newer."""
    date_match = DATE_RE.search(line)
    year = int(date_match.group(1)) if date_match else 0
    month = int(date_match.group(2)) if date_match else 0
    arxiv_match = ARXIV_RE.search(line)
    arxiv_num = 0
    if arxiv_match:
        parts = arxiv_match.group(1).split(".")
        if len(parts) == 2:
            try:
                arxiv_num = int(parts[1])
            except ValueError:
                pass
    return (year, month, arxiv_num)


def insert_entry(readme_text: str, paper: dict, category: str) -> str:
    """Insert a paper entry into the correct section, maintaining date-descending order."""
    lines = readme_text.split("\n")
    start, end = find_section_range(lines, category)
    entry_line = format_entry(paper)
    new_key = _parse_entry_sort_key(entry_line)
    # Find existing entries in this section
    insert_at = start + 1  # default: right after the heading
    for i in range(start + 1, end):
        if not lines[i].startswith("- "):
            if lines[i].strip() == "":
                continue
            break
        existing_key = _parse_entry_sort_key(lines[i])
        if new_key > existing_key:
            insert_at = i
            break
        insert_at = i + 1
    lines.insert(insert_at, entry_line)
    return "\n".join(lines)


def write_paper_to_readme(repo_path: Path, paper: dict, category: str) -> None:
    """Insert a paper entry into the repo's README.md and commit."""
    readme = repo_path / "README.md"
    text = readme.read_text(encoding="utf-8")
    updated = insert_entry(text, paper, category)
    readme.write_text(updated, encoding="utf-8")


def git_commit_and_push(repo_path: Path, paper_title: str) -> None:
    """Stage README.md, commit, and push."""
    subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True)
    msg = f"Add {paper_title}"
    subprocess.run(["git", "commit", "-m", msg], cwd=repo_path, check=True)
    subprocess.run(["git", "push"], cwd=repo_path, check=True)
