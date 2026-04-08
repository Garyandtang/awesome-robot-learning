"""Bootstrap taste profile from awesome-humanoid-robot-learning README."""

import re
from collections import Counter
from datetime import date
from pathlib import Path

import yaml

from scripts.fetch_paper import parse_arxiv_id

# Matches lines like: - [venue date](url), Title
# or: - 🌟[venue date](url), Title
# or: - 🌟 [venue date](url), Title, [website](project_url)
ENTRY_RE = re.compile(
    r"^- (?:🌟\s?)?\[([^\]]+)\]\(([^)]+)\),\s*(.+)$"
)
PROJECT_URL_RE = re.compile(r"\[website\]\(([^)]+)\)")
SECTION_RE = re.compile(r"^## (.+)$")
# Matches date patterns like "2026.03", "2025", "2024.12"
_DATE_RE = re.compile(r"\b(\d{4}(?:\.\d{2})?)\s*$")


def parse_awesome_list_entries(readme_text: str) -> list[dict]:
    """Parse paper entries from an awesome list README.

    Returns list of dicts with: title, url, arxiv_id, venue, date,
    has_code, project_url, category.
    """
    entries = []
    current_section = ""

    for line in readme_text.splitlines():
        section_match = SECTION_RE.match(line.strip())
        if section_match:
            current_section = section_match.group(1).strip()
            continue

        entry_match = ENTRY_RE.match(line.strip())
        if not entry_match:
            continue

        venue_date = entry_match.group(1).strip()
        url = entry_match.group(2).strip()
        rest = entry_match.group(3).strip()

        # Extract project URL if present
        project_url = None
        proj_match = PROJECT_URL_RE.search(rest)
        if proj_match:
            project_url = proj_match.group(1)
            rest = rest[:proj_match.start()].rstrip(", ")

        title = rest.strip()
        has_code = "🌟" in line
        arxiv_id = parse_arxiv_id(url) or ""

        # Parse venue and date from venue_date string like "arXiv 2026.03"
        # Handle multi-word venues: "RA-L 2024.01", "website 2025.11"
        date_match = _DATE_RE.search(venue_date)
        if date_match:
            date_str = date_match.group(1)
            venue = venue_date[:date_match.start()].strip()
        else:
            date_str = ""
            venue = venue_date

        entries.append({
            "title": title,
            "url": url,
            "arxiv_id": arxiv_id,
            "venue": venue,
            "date": date_str,
            "has_code": has_code,
            "project_url": project_url,
            "category": current_section,
            "authors": [],
        })

    return entries


def extract_author_stats(papers: list[dict]) -> dict[str, int]:
    """Count author appearances across papers."""
    counter: Counter[str] = Counter()
    for p in papers:
        for author in p.get("authors", []):
            if author:
                counter[author] += 1
    return dict(counter)


def build_initial_taste_profile(papers: list[dict]) -> dict:
    """Build an initial taste_profile.yaml structure from parsed papers."""
    author_stats = extract_author_stats(papers)
    top_authors = [
        {"name": name, "reason": f"冷启动：awesome-humanoid-robot-learning 中出现 {count} 次"}
        for name, count in sorted(author_stats.items(), key=lambda x: -x[1])
        if count >= 3
    ]

    cat_counter: Counter[str] = Counter()
    for p in papers:
        cat = p.get("category", "")
        if cat:
            cat_counter[cat] += 1
    top_categories = [
        {"category": cat, "count": count}
        for cat, count in cat_counter.most_common(10)
    ]

    return {
        "preferences": {
            "like": [],
            "dislike": [],
        },
        "authors_whitelist": top_authors,
        "authors_blacklist": [],
        "method_keywords_positive": [],
        "method_keywords_negative": [],
        "stats": {
            "total_collected": len(papers),
            "top_categories": top_categories,
            "last_updated": date.today().isoformat(),
        },
    }


def build_source_candidates(papers: list[dict]) -> dict:
    """Build initial source_candidates.yaml from author analysis."""
    author_stats = extract_author_stats(papers)
    top_authors = [
        (name, count)
        for name, count in sorted(author_stats.items(), key=lambda x: -x[1])
        if count >= 3
    ]
    candidates = [
        {
            "name": f"{name} (personal/lab blog)",
            "url": "",
            "discovered_via": "author_backtrack",
            "related_authors": [name],
            "relevance": f"awesome-humanoid-robot-learning 中出现 {count} 次",
            "status": "pending",
        }
        for name, count in top_authors[:20]
    ]
    return {"candidates": candidates}


def run_bootstrap(
    readme_path: Path,
    taste_output: Path,
    candidates_output: Path,
) -> dict:
    """Run the full bootstrap pipeline."""
    text = readme_path.read_text(encoding="utf-8")
    entries = parse_awesome_list_entries(text)

    profile = build_initial_taste_profile(entries)
    with open(taste_output, "w", encoding="utf-8") as f:
        yaml.dump(profile, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    candidates = build_source_candidates(entries)
    with open(candidates_output, "w", encoding="utf-8") as f:
        yaml.dump(candidates, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return {"entries": entries, "profile": profile, "candidates": candidates}


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent.parent
    humanoid_readme = Path("/home/gary/Documents/awesome-humanoid-robot-learning/README.md")
    taste_out = repo_root / "data" / "taste_profile.yaml"
    candidates_out = repo_root / "data" / "source_candidates.yaml"

    result = run_bootstrap(humanoid_readme, taste_out, candidates_out)
    print(f"Parsed {len(result['entries'])} entries")
    print(f"Taste profile written to {taste_out}")
    print(f"Source candidates written to {candidates_out}")
