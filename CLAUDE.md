# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A curated "awesome list" of academic papers about **robot learning**, maintained as a single `README.md`. Papers are categorized by task and sorted by date (newest first) within each section.

## Sections (in order)

1. Manipulation
2. Loco-Manipulation
3. VLA (Vision-Language-Action)
4. Force Control & Perception
5. Sim-to-Real
6. System & Foundation Model
7. Hardware

## Adding a Paper

Each entry follows this format:

```
- [<venue> <YYYY.MM>](<url>), <Paper Title>
```

Optional additions:
- `, [website](<project-page-url>)` suffix — if a project page exists
- `🌟 ` prefix before the `[venue]` bracket — if code is open-sourced (e.g., `- 🌟 [arXiv 2025.06](...)`)

**Venue prefix examples:** `arXiv 2026.02`, `ICLR 2026`, `CoRL 2025`, `ICRA 2025`, `website 2025.11`

**Ordering:** Within each section, entries are sorted by date descending (newest first), then by arXiv ID descending for the same month.

**Section choice:** Pick the section that best matches the paper's primary task.

## Scripts

- `scripts/fetch_paper.py` — Fetch paper metadata from arXiv or Semantic Scholar
- `scripts/search_papers.py` — Search for new papers (arXiv + Semantic Scholar)
- `scripts/zotero_client.py` — Write paper entries to Zotero
- `scripts/notion_client.py` — Write paper entries to Notion database
- `scripts/git_writer.py` — Insert paper entries into README.md
- `scripts/generate_wordcloud.py` — Regenerate word cloud from README titles
- `scripts/config.py` — Load config from `~/.config/paper-collector/config.yaml`

## Running Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Wordcloud Generation

```bash
python3 scripts/generate_wordcloud.py
```

## Commit Style

- `Add <Paper Name> paper`
- `Add <Venue> <Paper Name>`
- `Update wordcloud`
