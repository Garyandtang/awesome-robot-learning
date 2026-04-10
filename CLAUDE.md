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

## Conda Environment

This project uses a dedicated conda environment `paper-rec` for all Python dependencies (embedding models, torch, etc.).

```bash
# Activate environment
conda activate paper-rec

# Run tests (from project root)
python3 -m pytest tests/ -v --override-ini="addopts=" -p no:cacheprovider

# Run daily pipeline
python3 -m scripts.daily_pipeline
```

Note: The `--override-ini="addopts=" -p no:cacheprovider` flags are needed to avoid conflicts with the ROS pytest plugin installed system-wide.

## Scripts

- `scripts/fetch_paper.py` — Fetch paper metadata from arXiv or Semantic Scholar
- `scripts/search_papers.py` — Search for new papers (arXiv + Semantic Scholar)
- `scripts/daily_pipeline.py` — Daily paper recommendation pipeline orchestrator
- `scripts/taste_engine.py` — Three-level recommendation funnel (L1 hard rules, L2 embedding, L3 LLM)
- `scripts/embedding_store.py` — Local embedding model (jina-embeddings-v5-text-nano) and vector storage
- `scripts/bootstrap_embeddings.py` — Cold-start: build embedding corpus from awesome-list papers
- `scripts/raw_ingest.py` — Raw data ingest layer: fetch metadata + fulltext + repo README to `wiki/raw/`
- `scripts/wiki_compiler.py` — LLM-compiled research wiki (Karpathy method), includes v2 two-step compiler
- `scripts/index_builder.py` — Build wiki index files: INDEX.md, papers/INDEX.md, concepts/INDEX.md, TOPIC-MAP.md
- `scripts/feedback.py` — Feedback loop: update corpus, stats, and wiki after daily scoring
- `scripts/rss_fetcher.py` — RSS/Atom feed fetcher for blog posts
- `scripts/config.py` — Load config from `~/.config/paper-collector/config.yaml`
- `scripts/zotero_client.py` — Write paper entries to Zotero
- `scripts/notion_client.py` — Write paper entries to Notion database
- `scripts/git_writer.py` — Insert paper entries into README.md
- `scripts/ingest.py` — Manual paper ingest CLI: fetch raw data + compile to wiki
- `scripts/cold_start_force_vla.py` — Cold start: ingest + compile ~25 Force-VLA papers into wiki
- `scripts/generate_wordcloud.py` — Regenerate word cloud from README titles

## Running Tests

```bash
conda activate paper-rec
python3 -m pytest tests/ -v --override-ini="addopts=" -p no:cacheprovider
```

## Wordcloud Generation

```bash
python3 scripts/generate_wordcloud.py
```

## Wiki Knowledge Base (Karpathy Method)

The project includes an LLM-compiled research wiki at `wiki/`. This is the externalized knowledge base — the LLM is stateless, so the wiki serves as its persistent memory.

### Wiki Structure

```
wiki/
├── INDEX.md              # Global entry point with stats and recent papers
├── TOPIC-MAP.md          # Research topic hierarchy (LLM-maintained)
├── papers/
│   ├── INDEX.md          # All papers grouped by year
│   └── {arxiv_id}.md     # Individual paper analysis pages (中文)
├── concepts/
│   ├── INDEX.md          # All concepts alphabetically
│   └── {slug}.md         # Concept pages with cross-references
└── raw/
    └── papers/{arxiv_id}/
        ├── meta.yaml     # Structured metadata
        ├── fulltext.md   # Paper full text
        ├── images/       # Extracted figures (page{NNN}-img{MM}.{jpeg,png})
        ├── images.json   # Image manifest (page, index, path, w, h, ext, bytes)
        ├── formulas.md   # Heuristic formula candidates grouped by page
        └── repo-readme.md # GitHub repo README (if available)
```

### Wiki Navigation Protocol (for Q&A)

When answering research questions:
1. Start at `wiki/INDEX.md` for overview
2. Use `wiki/TOPIC-MAP.md` to find relevant topic clusters
3. Use `wiki/concepts/INDEX.md` to find concept pages
4. Read concept pages for cross-paper synthesis
5. Drill into `wiki/papers/{id}.md` for paper-specific details
6. Check `wiki/raw/papers/{id}/` for original metadata and fulltext

### Wiki Commands

```bash
# Ingest a paper into raw layer
python3 -c "from scripts.raw_ingest import ingest_paper; ingest_paper('2411.15753')"

# Compile a paper (raw → wiki, 2 LLM calls)
python3 -c "from scripts.wiki_compiler import compile_paper_v2; compile_paper_v2('2411.15753')"

# Rebuild all indexes
python3 -c "from scripts.index_builder import build_all_indexes; build_all_indexes()"
```

## Commit Style

- `Add <Paper Name> paper`
- `Add <Venue> <Paper Name>`
- `Update wordcloud`
