"""LLM-compiled research wiki following Karpathy's method."""

from __future__ import annotations

import json
import logging
import re
import subprocess
import time
from datetime import date
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

WIKI_DIR = Path("wiki")
PAPERS_DIR = WIKI_DIR / "papers"
CONCEPTS_DIR = WIKI_DIR / "concepts"
CATEGORIES_DIR = WIKI_DIR / "categories"


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def _call_claude(prompt: str, timeout: int = 300) -> str:
    """Call claude --print with a prompt and return stdout.

    Raises RuntimeError if claude exits non-zero.
    """
    result = subprocess.run(
        ["claude", "--print", "-p", prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Claude CLI error (code {result.returncode}): "
            f"{result.stderr.strip()[:200]}"
        )
    return result.stdout.strip()


def _slugify(text: str) -> str:
    """Convert text to a URL/filename-safe slug.

    'Diffusion Policy' -> 'diffusion-policy'
    'Sim-to-Real Transfer' -> 'sim-to-real-transfer'
    '  Whole  Body  Control  ' -> 'whole-body-control'
    """
    slug = text.lower().strip()
    # Replace spaces with hyphens
    slug = re.sub(r"\s+", "-", slug)
    # Remove characters that are not alphanumeric or hyphens
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    # Collapse multiple hyphens
    slug = re.sub(r"-+", "-", slug)
    # Strip leading/trailing hyphens
    slug = slug.strip("-")
    return slug


def _extract_json(raw: str) -> str:
    """Extract JSON from raw LLM output, handling ```json fences."""
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if match:
        return match.group(1).strip()
    return raw


def _load_concept_aliases(wiki_dir: Path = WIKI_DIR) -> dict[str, list[str]]:
    """Load concept canonical-name aliases from wiki/concepts/_aliases.yaml.

    Returns {canonical_slug: [alias, ...]} or empty dict if file missing or malformed.
    """
    path = wiki_dir / "concepts" / "_aliases.yaml"
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        logger.warning("Failed to parse %s", path)
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: list(v) if isinstance(v, list) else [] for k, v in data.items()}


def _format_aliases_for_prompt(aliases: dict[str, list[str]]) -> str:
    """Format aliases dict as a prompt block guiding canonical concept naming.

    Returns an empty string when aliases is empty so the prompt can omit the
    whole section.
    """
    if not aliases:
        return ""
    lines = [
        "",
        "### 概念规范化（canonical names）",
        "",
        "如果论文提到以下任一 alias，请在 frontmatter `concepts[].name` 中统一使用左侧 canonical 名，不要创造新变体：",
        "",
    ]
    for canonical in sorted(aliases):
        alias_list = aliases[canonical]
        if alias_list:
            aliases_str = ", ".join(alias_list)
            lines.append(f"- **{canonical}** ← {aliases_str}")
        else:
            lines.append(f"- **{canonical}**")
    lines.append("")
    lines.append("上表之外的概念可以新建，使用描述性 kebab-case slug（如 `force-torque-sensing`）。")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompt builders (THE HEART OF KARPATHY'S METHOD)
# ---------------------------------------------------------------------------


def _build_paper_prompt(paper: dict, existing_concepts: list[str]) -> str:
    """Build prompt for paper page.

    Uses full text if available (_fulltext field), otherwise falls back to abstract.
    """
    concepts_context = ""
    if existing_concepts:
        concepts_context = f"""
以下是知识库中已有的研究概念，如果这篇论文与其中某些概念相关，请在分析中建立联系：
{chr(10).join(f'- {c}' for c in existing_concepts[:30])}
"""
    fulltext = paper.get("_fulltext", "")
    if fulltext:
        # Truncate to ~60K chars to leave room for prompt overhead
        content_block = f"- 论文全文（截取）:\n\n{fulltext[:60000]}"
    else:
        content_block = f"- 摘要: {paper.get('abstract', '无摘要')}"

    return f"""你是一个机器人学习领域的研究助手。请为以下论文撰写一篇深度分析文章（中文）。

## 论文信息
- 标题: {paper['title']}
- 作者: {', '.join(paper.get('authors', ['未知']))}
- 发表: {paper.get('venue', '未知')} {paper.get('date', '')}
- 链接: {paper.get('url', '')}
{content_block}
{concepts_context}

## 要求

请按以下结构撰写（使用 Markdown 格式）：

### 核心方法
详细描述论文提出的方法。不是复述摘要，而是用你的理解解释方法的核心思想、架构设计、关键组件。

### 关键创新
这篇论文相比已有工作的主要创新点是什么？解决了什么之前未解决的问题？

### 与已有工作的联系
这篇论文与领域内其他重要工作的关系。它延伸了哪些方法？与哪些工作互补？
（如果上面列出了已有概念，请明确指出与哪些概念相关）

### 局限性与未来方向
基于你的理解，这篇论文可能存在的局限性，以及潜在的改进方向。

### 研究意义
这篇论文对机器人学习领域的贡献和影响。

---
注意：
1. 全文使用中文
2. 分析要深入且具体，不要泛泛而谈
3. 使用 [[概念名]] 格式创建到概念页面的 Obsidian 链接
4. 文章开头加上 YAML frontmatter：
```yaml
---
title: "{paper['title']}"
arxiv_id: "{paper.get('arxiv_id', '')}"
date: "{paper.get('date', '')}"
venue: "{paper.get('venue', '')}"
compiled: "{date.today().isoformat()}"
concepts: []
---
```

重要：直接输出 Markdown 文章内容，不要输出任何解释、对话、或元评论。"""


def _build_concept_extraction_prompt(
    paper: dict, existing_concepts: list[str]
) -> str:
    """Build prompt for concept extraction."""
    existing_block = ""
    if existing_concepts:
        existing_block = f"""
## 已有概念列表
以下概念已经存在于知识库中。如果论文涉及这些概念，请直接使用已有名称（不要创建重复概念）：
{chr(10).join(f'- {c}' for c in existing_concepts)}
"""
    return f"""你是一个机器人学习领域的研究助手。请从以下论文中识别核心研究概念。

## 论文信息
- 标题: {paper['title']}
- 摘要: {paper.get('abstract', '无摘要')}
{existing_block}

## 要求

识别这篇论文涉及的 3-7 个核心研究概念。这些概念应该是：
1. **高层次的研究主题**，不是具体的技术细节
2. **可复用的**——其他论文也可能涉及这些概念
3. **有意义的**——能帮助理解这篇论文在领域中的位置

概念名称使用英文（方便作为文件名），但要确保准确反映研究内容。

## 输出格式

输出严格的 JSON 数组，每个元素是一个概念名称字符串：
```json
["Diffusion Policy", "Sim-to-Real Transfer", "Whole-Body Control"]
```

只输出 JSON 数组，不要输出其他内容。"""


def _build_concept_creation_prompt(concept: str, paper: dict) -> str:
    """Build prompt for concept creation."""
    return f"""你是一个机器人学习领域的研究助手。请为以下研究概念撰写一篇知识库文章（中文）。

## 概念名称
{concept}

## 来源论文
- 标题: {paper['title']}
- 摘要: {paper.get('abstract', '无摘要')}
- 链接: {paper.get('url', '')}

## 要求

请撰写一篇关于「{concept}」的综述性文章。这篇文章应该：

1. **解释概念本身**：什么是 {concept}？它解决什么问题？核心思想是什么？
2. **历史与发展**：这个概念的起源和重要里程碑
3. **在来源论文中的应用**：上述论文如何使用或推进了这个概念
4. **与其他概念的关系**：它与领域内其他重要概念的联系

## 格式

使用 Markdown，文章开头加上 YAML frontmatter：
```yaml
---
concept: "{concept}"
created: "{date.today().isoformat()}"
updated: "{date.today().isoformat()}"
papers:
  - "{paper.get('arxiv_id', paper['title'])}"
---
```

使用 [[论文标题]] 格式创建到论文页面的 Obsidian 链接。
全文使用中文。

重要：直接输出 Markdown 文章内容，不要输出任何解释、对话、或元评论。"""


def _build_concept_update_prompt(
    concept: str, existing_content: str, new_paper: dict
) -> str:
    """Build prompt for concept update (incremental compilation)."""
    return f"""你是一个机器人学习领域的研究助手。请更新以下知识库文章。

## 当前文章内容

```markdown
{existing_content}
```

## 新论文

一篇新论文涉及了「{concept}」这个概念：
- 标题: {new_paper['title']}
- 摘要: {new_paper.get('abstract', '无摘要')}
- 链接: {new_paper.get('url', '')}
- arXiv ID: {new_paper.get('arxiv_id', '')}

## 要求

请输出**更新后的完整文章**（不是增量diff）。更新应该：

1. 在 frontmatter 的 papers 列表中添加新论文
2. 更新 frontmatter 的 updated 日期为 {date.today().isoformat()}
3. 将新论文的贡献融入到文章中——不是简单追加一段，而是有机地整合
4. 如果新论文提供了新的视角或进展，更新相关段落
5. 如果新论文与已有论文形成对比或互补，建立这些联系
6. 保持文章的整体结构和连贯性

全文使用中文。输出完整的更新后文章（包括 frontmatter）。

重要：直接输出 Markdown 文章内容，不要输出任何解释、对话、或元评论。"""


# ---------------------------------------------------------------------------
# Paper Pages (LLM-written)
# ---------------------------------------------------------------------------


def compile_paper_page(
    paper: dict, wiki_dir: Path = WIKI_DIR
) -> Path:
    """Have Claude write a deep analysis page for a paper.

    Fetches full text (HTML → PDF fallback) before generating analysis.
    Returns path to the written .md file.
    """
    papers_dir = wiki_dir / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)

    # Fetch full text if not already present
    if "_fulltext" not in paper:
        from scripts.fetch_paper import fetch_fulltext
        arxiv_id = paper.get("arxiv_id", "")
        if arxiv_id:
            fulltext = fetch_fulltext(arxiv_id)
            if fulltext:
                paper = {**paper, "_fulltext": fulltext}

    existing_concepts = get_concept_index(wiki_dir)
    prompt = _build_paper_prompt(paper, existing_concepts)
    content = _call_claude(prompt)

    # Use arxiv_id as filename if available, otherwise slugify title
    arxiv_id = paper.get("arxiv_id", "")
    if arxiv_id:
        filename = f"{arxiv_id}.md"
    else:
        filename = f"{_slugify(paper['title'])}.md"

    output_path = papers_dir / filename
    output_path.write_text(content, encoding="utf-8")
    logger.info("Compiled paper page: %s", output_path)
    return output_path


# ---------------------------------------------------------------------------
# Concept Extraction (LLM-powered)
# ---------------------------------------------------------------------------


def extract_concepts_llm(
    paper: dict, wiki_dir: Path = WIKI_DIR
) -> list[str]:
    """Have Claude identify core concepts from a paper.

    Returns list of concept names. Returns empty list on parse failure.
    """
    existing_concepts = get_concept_index(wiki_dir)
    prompt = _build_concept_extraction_prompt(paper, existing_concepts)

    try:
        raw_output = _call_claude(prompt)
    except RuntimeError:
        logger.warning("Concept extraction failed for: %s", paper.get("title", ""))
        return []

    # Parse JSON — handle ```json wrapping
    json_text = _extract_json(raw_output)

    try:
        concepts = json.loads(json_text)
    except (json.JSONDecodeError, TypeError):
        logger.warning(
            "Failed to parse concept extraction output for: %s",
            paper.get("title", ""),
        )
        return []

    # Validate: must be a list of strings
    if not isinstance(concepts, list):
        return []
    return [c for c in concepts if isinstance(c, str)]


# ---------------------------------------------------------------------------
# Concept Pages (LLM-written, incrementally updated)
# ---------------------------------------------------------------------------


def create_concept_page(
    concept: str, source_paper: dict, wiki_dir: Path = WIKI_DIR
) -> Path:
    """Have Claude write a NEW concept article.

    Returns path to the written .md file.
    """
    concepts_dir = wiki_dir / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)

    prompt = _build_concept_creation_prompt(concept, source_paper)
    content = _call_claude(prompt)

    filename = f"{_slugify(concept)}.md"
    output_path = concepts_dir / filename
    output_path.write_text(content, encoding="utf-8")
    logger.info("Created concept page: %s", output_path)
    return output_path


def update_concept_page(
    concept: str, new_paper: dict, wiki_dir: Path = WIKI_DIR
) -> Path:
    """Have Claude UPDATE existing concept article with new paper.

    Returns path to the updated .md file.
    """
    concepts_dir = wiki_dir / "concepts"
    filename = f"{_slugify(concept)}.md"
    concept_path = concepts_dir / filename

    existing_content = concept_path.read_text(encoding="utf-8")

    prompt = _build_concept_update_prompt(concept, existing_content, new_paper)
    updated_content = _call_claude(prompt)

    concept_path.write_text(updated_content, encoding="utf-8")
    logger.info("Updated concept page: %s", concept_path)
    return concept_path


# ---------------------------------------------------------------------------
# Index Pages (template-based)
# ---------------------------------------------------------------------------


def build_index_pages(wiki_dir: Path = WIKI_DIR) -> None:
    """Rebuild all index files: INDEX.md, papers/INDEX.md, concepts/INDEX.md, TOPIC-MAP.md, and README.md."""
    from scripts.index_builder import build_all_indexes

    build_all_indexes(wiki_dir)

    # Also keep legacy README and category indexes
    build_wiki_readme(wiki_dir)

    categories_dir = wiki_dir / "categories"
    categories_dir.mkdir(parents=True, exist_ok=True)

    categories: dict[str, list[dict]] = {}
    papers_dir = wiki_dir / "papers"
    if papers_dir.is_dir():
        for md_file in sorted(papers_dir.glob("*.md")):
            content = md_file.read_text(encoding="utf-8")
            venue = _extract_frontmatter_field(content, "venue")
            if venue:
                categories.setdefault(venue, []).append(
                    {"file": md_file.name, "title": _extract_frontmatter_field(content, "title") or md_file.stem}
                )

    for category in categories:
        build_category_index(category, wiki_dir)


def build_wiki_readme(wiki_dir: Path = WIKI_DIR) -> None:
    """Build the wiki home page (README.md)."""
    papers_dir = wiki_dir / "papers"
    concepts_dir = wiki_dir / "concepts"
    categories_dir = wiki_dir / "categories"

    paper_count = len(list(papers_dir.glob("*.md"))) if papers_dir.is_dir() else 0
    concept_count = len(list(concepts_dir.glob("*.md"))) if concepts_dir.is_dir() else 0

    # Collect paper links
    paper_links: list[str] = []
    if papers_dir.is_dir():
        for md_file in sorted(papers_dir.glob("*.md")):
            title = _extract_frontmatter_field(
                md_file.read_text(encoding="utf-8"), "title"
            ) or md_file.stem
            paper_links.append(f"- [{title}](papers/{md_file.name})")

    # Collect concept links
    concept_links: list[str] = []
    if concepts_dir.is_dir():
        for md_file in sorted(concepts_dir.glob("*.md")):
            name = md_file.stem.replace("-", " ").title()
            concept_links.append(f"- [{name}](concepts/{md_file.name})")

    today = date.today().isoformat()

    readme_content = f"""# Robot Learning Research Wiki

> LLM-compiled knowledge base following Karpathy's method.
> Last updated: {today}

## Stats

- Papers: {paper_count}
- Concepts: {concept_count}

## Papers

{chr(10).join(paper_links) if paper_links else "_No papers yet._"}

## Concepts

{chr(10).join(concept_links) if concept_links else "_No concepts yet._"}
"""

    readme_path = wiki_dir / "README.md"
    readme_path.write_text(readme_content, encoding="utf-8")
    logger.info("Built wiki README: %s", readme_path)


def build_category_index(
    category: str, wiki_dir: Path = WIKI_DIR
) -> None:
    """Build a category index page."""
    categories_dir = wiki_dir / "categories"
    categories_dir.mkdir(parents=True, exist_ok=True)
    papers_dir = wiki_dir / "papers"

    # Find papers matching this category/venue
    paper_links: list[str] = []
    if papers_dir.is_dir():
        for md_file in sorted(papers_dir.glob("*.md")):
            content = md_file.read_text(encoding="utf-8")
            venue = _extract_frontmatter_field(content, "venue")
            if venue and venue.lower() == category.lower():
                title = _extract_frontmatter_field(content, "title") or md_file.stem
                paper_links.append(f"- [{title}](../papers/{md_file.name})")

    category_content = f"""# {category}

## Papers

{chr(10).join(paper_links) if paper_links else "_No papers in this category yet._"}
"""

    filename = f"{_slugify(category)}.md"
    output_path = categories_dir / filename
    output_path.write_text(category_content, encoding="utf-8")
    logger.info("Built category index: %s", output_path)


def _extract_frontmatter_field(content: str, field: str) -> str | None:
    """Extract a field value from YAML frontmatter."""
    # Match frontmatter block
    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        return None
    frontmatter = fm_match.group(1)
    # Simple line-based extraction
    pattern = rf'^{re.escape(field)}:\s*"?([^"\n]*)"?\s*$'
    match = re.search(pattern, frontmatter, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


# ---------------------------------------------------------------------------
# Batch Operations
# ---------------------------------------------------------------------------


def compile_wiki_batch(
    papers: list[dict],
    wiki_dir: Path = WIKI_DIR,
    max_papers: int = 10,
) -> dict:
    """Batch compile: for each paper, compile page + extract concepts + create/update concept pages.

    Returns: {papers_compiled, concepts_created, concepts_updated}
    """
    stats = {
        "papers_compiled": 0,
        "concepts_created": 0,
        "concepts_updated": 0,
    }

    for paper in papers[:max_papers]:
        title = paper.get("title", "unknown")
        logger.info("Compiling paper: %s", title)

        # 1. Compile paper page
        try:
            compile_paper_page(paper, wiki_dir)
            stats["papers_compiled"] += 1
        except Exception:
            logger.exception("Failed to compile paper page: %s", title)
            continue

        # 2. Extract concepts
        try:
            concepts = extract_concepts_llm(paper, wiki_dir)
        except Exception:
            logger.exception("Failed to extract concepts for: %s", title)
            concepts = []

        # 3. Create or update concept pages
        existing_concepts = get_concept_index(wiki_dir)
        for concept in concepts:
            slug = _slugify(concept)
            concept_path = wiki_dir / "concepts" / f"{slug}.md"
            try:
                if concept_path.exists():
                    update_concept_page(concept, paper, wiki_dir)
                    stats["concepts_updated"] += 1
                else:
                    create_concept_page(concept, paper, wiki_dir)
                    stats["concepts_created"] += 1
            except Exception:
                logger.exception(
                    "Failed to create/update concept '%s' for paper: %s",
                    concept,
                    title,
                )

        # Rate limit between papers
        time.sleep(1)

    # Rebuild index pages
    try:
        build_index_pages(wiki_dir)
    except Exception:
        logger.exception("Failed to build index pages")

    logger.info(
        "Wiki batch complete: %d papers, %d concepts created, %d concepts updated",
        stats["papers_compiled"],
        stats["concepts_created"],
        stats["concepts_updated"],
    )
    return stats


# ---------------------------------------------------------------------------
# V2 Two-Step Compilation (Karpathy Method redesign)
# ---------------------------------------------------------------------------

_MAX_FULLTEXT_V2 = 60_000  # ~15K tokens for Step 1 prompt


def _build_step1_prompt(
    raw_content: dict,
    concepts_index: str,
    topic_map: str,
    aliases_block: str = "",
) -> str:
    """Build Step 1 prompt: Understand + Analyze + Classify.

    raw_content: from raw_ingest.load_raw_content() — {meta, fulltext, repo_readme}
    concepts_index: content of concepts/INDEX.md (or empty)
    topic_map: content of TOPIC-MAP.md (or empty)
    aliases_block: pre-formatted canonical concept name block
        (see _format_aliases_for_prompt). Empty string means no aliases section.
    """
    meta = raw_content["meta"]
    fulltext = raw_content.get("fulltext") or ""
    repo_readme = raw_content.get("repo_readme") or ""
    assets = meta.get("assets") or []

    meta_block = (
        f"标题: {meta['title']}\n"
        f"作者: {', '.join(meta.get('authors', []))}\n"
        f"日期: {meta.get('date', '')}\n"
        f"发表: {meta.get('venue', 'arXiv')}\n"
        f"链接: {meta.get('url', '')}"
    )

    content_block = fulltext[:_MAX_FULLTEXT_V2] if fulltext else f"摘要: {meta.get('abstract', '无全文和摘要')}"
    repo_block = f"\n\n## Repo README\n\n{repo_readme[:10000]}" if repo_readme else ""

    # Surface non-text raw assets so the compiler knows they exist.
    asset_notes: list[str] = []
    if "images.json" in assets:
        asset_notes.append(
            f"图片: 原始图片存于 raw/papers/{meta['id']}/images/，清单见 raw/papers/{meta['id']}/images.json"
        )
    if "formulas.md" in assets:
        asset_notes.append(
            f"公式候选: raw/papers/{meta['id']}/formulas.md (启发式抽取的数学行)"
        )
    assets_block = ("\n\n### 附加原始素材\n" + "\n".join(f"- {n}" for n in asset_notes)) if asset_notes else ""

    concepts_block = f"\n### 概念索引\n{concepts_index}" if concepts_index.strip() else "\n### 概念索引\n（空，知识库尚无概念）"
    topic_block = f"\n### 主题地图\n{topic_map}" if topic_map.strip() else "\n### 主题地图\n（空，知识库尚无主题地图）"

    today = date.today().isoformat()

    return f"""你是一个研究知识库的编译器。你的任务是分析一篇新论文，将它编译成知识库的一个页面。

## 原始数据

{meta_block}

{content_block}
{repo_block}
{assets_block}

## 知识库当前状态
{concepts_block}
{topic_block}
{aliases_block}

## 输出要求

输出一个完整的 Markdown 文件，包含两部分：

### Part A: YAML Frontmatter

必须包含以下字段：
- title, arxiv_id, date, venue, authors, url
- repo_url（如有）
- raw: "raw/papers/{meta['id']}"
- compiled: "{today}"
- summary: 一句话摘要（中文，<100字，供索引使用）
- concepts: 数组，每个元素包含：
  - name: 概念名（英文，使用知识库中已有名称优先）
  - relation: extends | compares | uses | introduces
  - detail: 一句话说明关系（中文）
- new_concepts: 数组（只包含知识库中不存在的新概念），每个元素包含：
  - name: 概念名
  - suggested_topic: 在主题地图中的建议位置（格式："父主题 > 子主题"）
  - description: 一行描述（中文，供索引使用）

### Part B: 正文（深度分析）

写一篇深度分析文章（中文），让该领域的研究者读完后能理解：
- 这篇论文做了什么
- 为什么重要
- 和已有工作什么关系
- 有什么局限

要求：
1. 用 [[概念名]] 格式创建 Obsidian 反向链接
2. 关系要 typed：明确写"延伸了 [[X]]"、"对比 [[Y]]"、"使用了 [[Z]]"
3. 如果有 repo，分析实现细节和论文描述的异同
4. 不要使用固定模板——根据论文类型（方法/系统/综述）自行组织最合适的结构
5. 分析要深入具体，不要泛泛而谈
6. 直接输出 Markdown，不要输出解释、对话或元评论"""


def _build_step2_prompt(
    step1_frontmatter: dict,
    step1_body_preview: str,
    concept_pages: dict[str, str],
    new_concepts: list[dict],
) -> str:
    """Build Step 2 prompt: Knowledge Integration.

    step1_frontmatter: parsed YAML dict from Step 1 output
    step1_body_preview: first 3000 chars of Step 1 body
    concept_pages: {concept_name: existing page content}
    new_concepts: list of {name, suggested_topic, description}
    """
    fm_text = yaml.dump(step1_frontmatter, allow_unicode=True, sort_keys=False, default_flow_style=False)

    existing_block = ""
    for name, content in concept_pages.items():
        # Truncate each concept page to keep context manageable
        truncated = content[:5000]
        existing_block += f"\n### 概念: {name}\n```markdown\n{truncated}\n```\n"

    new_block = ""
    if new_concepts:
        items = "\n".join(
            f"- {nc['name']}: {nc.get('description', '')}（建议位置: {nc.get('suggested_topic', '未分类')}）"
            for nc in new_concepts
        )
        new_block = f"\n## 需要新建的概念页\n\n{items}\n"

    today = date.today().isoformat()

    return f"""你是一个研究知识库的编译器。一篇新论文刚刚被编译到知识库中。
你的任务是将新论文的知识整合到相关的概念页面中。

## 新编译的论文

### Frontmatter
{fm_text}

### 分析摘要
{step1_body_preview}

## 需要更新的概念页
{existing_block if existing_block else "（无需更新的已有概念页）"}
{new_block}

## 什么才算"概念"（关键判据）

概念页是**跨论文可复用的知识单元**，而不是某篇论文独有的贡献或命名。判断一个候选概念是否应该建页：

- **应该建**：这个术语/方法/原理可能出现在未来 ≥3 篇论文里（例：impedance control、diffusion policy、force-torque sensing、CFG、action chunking）
- **不应建**：它只是本论文的某个架构组件或新命名（例：某论文的 dual-path tactile encoder、asymmetric tokenizer、某篇的 reward 项名字）——这些内容应该**留在论文页里**作为方法细节，不要升格为独立概念页
- **边界情况**：若该术语是本论文的**核心贡献且已被后续工作引用**（例：VIB、RDT-1B、RLHF），可以建页，但必须在页面正文明确说明来源论文

如果"需要新建的概念页"列表里出现了明显是论文专属贡献的条目，**直接跳过它**（不要输出 `===NEW_CONCEPT:` 块），不要为它创建概念页。宁可少建，不要建垃圾。

## 输出要求

对每个概念输出更新/新建后的完整页面，用分隔符区分：

对于**已有概念**：
===CONCEPT: {{概念名}}===
<frontmatter 和正文，不要任何 markdown 代码块围栏>

对于**新概念**：
===NEW_CONCEPT: {{概念名}}===
<frontmatter 和正文，不要任何 markdown 代码块围栏>

**重要的格式约束（违反会导致编译失败）**：
1. **绝对不要**在 `===CONCEPT:` 和下一个 `===CONCEPT:` 之间用 ```` ```markdown ```` 或 ```` ``` ```` 包裹内容——直接输出纯 Markdown
2. **绝对不要**在整个响应外围包一层代码块
3. **绝对不要**输出空概念名 `===CONCEPT:  ===`——要么给出真实名字，要么跳过
4. **绝对不要**在 `===CONCEPT:` 行后添加解释或对话

### 更新策略

已有概念页的更新必须是**有机整合**，不是追加：
- 新论文推进了该概念 → 融入"发展历程"
- 新论文应用该概念到新场景 → 扩展"应用"
- 新论文对比/改进了已有方法 → 更新对比分析
- 新论文解决了已提到的局限 → 更新局限性讨论

### 概念页 frontmatter 格式

---
concept: "概念名"
created: "首次创建日期"
updated: "{today}"
papers:
  - "arxiv_id_1"
  - "arxiv_id_2"
parent_topic: "主题地图中的父主题"
description: "一行描述（中文，供索引使用）"
---

### 概念页正文要求

1. 使用 [[论文标题]] 或 [[arxiv_id]] 创建反向链接
2. 全文中文
3. 不要简单追加段落——重新组织使内容连贯
4. 直接输出 Markdown，不要输出解释、对话或元评论"""


def _parse_step1_output(raw_output: str) -> dict:
    """Parse Step 1 LLM output into {frontmatter: dict, body: str}.

    Tolerant of common LLM output variations:
    - leading preamble text before the frontmatter
    - markdown code fence wrappers (```markdown ... ``` or ```md ... ```)
    - nested fences that confuse a naive regex

    Strategy: strip all standalone code-fence lines (``` on their own line,
    optionally with a language tag), then search for the first `---...---`
    block that contains valid YAML with a `title` field. Try subsequent
    candidates if the first one fails — this handles cases where Claude
    emits spurious `---` separators before the real frontmatter.

    Raises ValueError if parsing fails.
    """
    text = raw_output.strip()

    # Drop standalone code-fence lines like ``` or ```markdown or ```yaml.
    # These are never part of frontmatter or body for our purpose and only
    # confuse frontmatter matching.
    cleaned_lines = [
        line for line in text.splitlines()
        if not re.match(r"^\s*```[a-zA-Z0-9_+-]*\s*$", line)
    ]
    text = "\n".join(cleaned_lines).strip()

    # Find all `---\n...\n---` candidates, trying each until one yields a
    # valid YAML dict with at least a `title` field.
    pattern = re.compile(
        r"(?:^|\n)---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)",
        re.DOTALL,
    )

    last_error: Exception | None = None
    for match in pattern.finditer(text):
        fm_text = match.group(1)
        body = text[match.end():].strip()

        try:
            frontmatter = yaml.safe_load(fm_text)
        except yaml.YAMLError as exc:
            last_error = exc
            continue

        if not isinstance(frontmatter, dict):
            continue

        # Must have at least a title to be real frontmatter (not a markdown
        # horizontal rule that happened to look like a delimiter).
        if "title" not in frontmatter:
            continue

        return {"frontmatter": frontmatter, "body": body}

    if last_error is not None:
        raise ValueError(f"Invalid YAML in Step 1 frontmatter: {last_error}") from last_error
    raise ValueError("Step 1 output has no YAML frontmatter")


def _strip_code_fence(text: str) -> str:
    """Strip a leading/trailing markdown code fence that wraps the whole block.

    LLMs occasionally wrap their entire output in ```markdown ... ``` even when
    asked not to. We only strip a fence that brackets the whole content; fences
    that appear mid-content (legitimate code blocks) are left intact.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    # Match opening fence: ``` optionally followed by a language tag, then newline
    m = re.match(r"^```[^\n]*\n", stripped)
    if not m:
        return stripped
    without_open = stripped[m.end():]

    # Match closing fence: optional trailing newline + ```
    close_match = re.search(r"\n?```\s*$", without_open)
    if not close_match:
        return stripped  # unbalanced — leave alone
    return without_open[: close_match.start()].strip()


def _parse_step2_output(raw_output: str) -> list[dict]:
    """Parse Step 2 LLM output into list of concept dicts.

    Returns list of {name: str, content: str, is_new: bool}.

    Robust to:
    - LLM wrapping the whole output in ```markdown ... ``` fences
    - Individual concept blocks being wrapped in code fences
    - Empty concept names (===CONCEPT:  ===) — these are skipped
    """
    results: list[dict] = []

    # If the LLM wrapped the entire response in a markdown code fence, strip it.
    cleaned = _strip_code_fence(raw_output)

    # Split on ===CONCEPT: or ===NEW_CONCEPT: delimiters
    pattern = r"===(?:(NEW_)?CONCEPT):\s*(.+?)===\s*\n?"
    parts = re.split(pattern, cleaned)

    # parts will be: [preamble, is_new_1|None, name_1, content_1, is_new_2|None, name_2, content_2, ...]
    i = 1  # skip preamble
    while i + 2 < len(parts):
        is_new = parts[i] is not None  # "NEW_" matched or None
        name = parts[i + 1].strip()
        content = _strip_code_fence(parts[i + 2])
        # Skip entries with empty names (caused `.md` garbage file in wiki/concepts/)
        if name and content:
            results.append({
                "name": name,
                "content": content,
                "is_new": is_new,
            })
        i += 3

    return results


def compile_paper_v2(
    arxiv_id: str,
    wiki_dir: Path = WIKI_DIR,
) -> dict:
    """Two-step compilation: Understand+Analyze → Knowledge Integration.

    Reads from raw layer, writes paper page and concept pages.
    Returns {paper_page, concepts_updated, concepts_created, frontmatter}.
    """
    from scripts.raw_ingest import load_raw_content, load_raw_meta

    # 1. Load raw content
    raw_content = load_raw_content(arxiv_id, wiki_dir)
    meta = raw_content["meta"]

    # 2. Load current wiki context
    concepts_index_path = wiki_dir / "concepts" / "INDEX.md"
    concepts_index = concepts_index_path.read_text(encoding="utf-8") if concepts_index_path.exists() else ""

    topic_map_path = wiki_dir / "TOPIC-MAP.md"
    topic_map = topic_map_path.read_text(encoding="utf-8") if topic_map_path.exists() else ""

    # 3. Step 1: Understand + Analyze + Classify
    aliases = _load_concept_aliases(wiki_dir)
    aliases_block = _format_aliases_for_prompt(aliases)
    step1_prompt = _build_step1_prompt(
        raw_content, concepts_index, topic_map, aliases_block=aliases_block
    )
    logger.info("Step 1: analyzing %s (%s)", arxiv_id, meta["title"])
    step1_output = _call_claude(step1_prompt, timeout=1200)

    try:
        parsed = _parse_step1_output(step1_output)
    except ValueError:
        # Dump raw output to disk for post-mortem debugging, then re-raise.
        debug_path = wiki_dir / "raw" / "papers" / arxiv_id / "_step1_debug.txt"
        try:
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            debug_path.write_text(step1_output, encoding="utf-8")
            logger.error("Dumped unparseable Step 1 output to %s", debug_path)
        except Exception:
            logger.exception("Failed to dump Step 1 debug output")
        raise
    frontmatter = parsed["frontmatter"]
    body = parsed["body"]

    # Write paper page — reassemble from parsed parts so any LLM preamble
    # or code-fence wrapping is stripped, leaving a clean frontmatter+body.
    fm_yaml = yaml.dump(frontmatter, allow_unicode=True, sort_keys=False, default_flow_style=False)
    paper_content = f"---\n{fm_yaml}---\n\n{body}\n"

    papers_dir = wiki_dir / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)
    paper_path = papers_dir / f"{arxiv_id}.md"
    paper_path.write_text(paper_content, encoding="utf-8")
    logger.info("Wrote paper page: %s", paper_path)

    # 4. Prepare Step 2
    concepts_in_fm = frontmatter.get("concepts", [])
    new_concepts_in_fm = frontmatter.get("new_concepts", [])

    # Collect existing concept pages that need updating
    concept_pages: dict[str, str] = {}
    concepts_dir = wiki_dir / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)

    for c in concepts_in_fm:
        concept_name = c["name"] if isinstance(c, dict) else c
        slug = _slugify(concept_name)
        concept_path = concepts_dir / f"{slug}.md"
        if concept_path.exists():
            concept_pages[concept_name] = concept_path.read_text(encoding="utf-8")

    # 5. Step 2: Knowledge Integration (skip if no concepts to process)
    concepts_updated = 0
    concepts_created = 0

    if concept_pages or new_concepts_in_fm:
        body_preview = body[:3000]
        step2_prompt = _build_step2_prompt(
            frontmatter, body_preview, concept_pages, new_concepts_in_fm,
        )
        logger.info("Step 2: integrating %d existing + %d new concepts",
                     len(concept_pages), len(new_concepts_in_fm))

        try:
            step2_output = _call_claude(step2_prompt, timeout=1200)
            concept_results = _parse_step2_output(step2_output)

            for cr in concept_results:
                slug = _slugify(cr["name"])
                concept_path = concepts_dir / f"{slug}.md"
                concept_path.write_text(cr["content"], encoding="utf-8")
                if cr["is_new"]:
                    concepts_created += 1
                    logger.info("Created concept: %s", cr["name"])
                else:
                    concepts_updated += 1
                    logger.info("Updated concept: %s", cr["name"])

        except Exception:
            # Fallback: use old individual concept compilation
            logger.warning("Step 2 failed, falling back to individual concept compilation")
            paper_dict = {
                "title": meta["title"],
                "authors": meta.get("authors", []),
                "abstract": "",
                "url": meta.get("url", ""),
                "arxiv_id": meta["id"],
            }
            for name, existing_content in concept_pages.items():
                try:
                    update_concept_page(name, paper_dict, wiki_dir)
                    concepts_updated += 1
                except Exception:
                    logger.exception("Fallback: failed to update concept %s", name)
            for nc in new_concepts_in_fm:
                try:
                    create_concept_page(nc["name"], paper_dict, wiki_dir)
                    concepts_created += 1
                except Exception:
                    logger.exception("Fallback: failed to create concept %s", nc["name"])

    # 6. Update raw meta.yaml compile status
    raw_meta = load_raw_meta(arxiv_id, wiki_dir)
    if raw_meta:
        raw_meta["compile_status"] = {
            "compiled_at": date.today().isoformat(),
            "wiki_page": f"papers/{arxiv_id}.md",
            "stale": False,
        }
        raw_dir = wiki_dir / "raw" / "papers" / arxiv_id
        meta_path = raw_dir / "meta.yaml"
        with open(meta_path, "w", encoding="utf-8") as f:
            yaml.dump(raw_meta, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    return {
        "paper_page": paper_path,
        "concepts_updated": concepts_updated,
        "concepts_created": concepts_created,
        "frontmatter": frontmatter,
    }


def rebuild_topic_map_llm(
    wiki_dir: Path = WIKI_DIR,
    timeout: int = 600,
) -> Path:
    """Rebuild wiki/TOPIC-MAP.md as a hierarchical topic map via LLM.

    Reads all concept pages' frontmatter + first ~500 chars of body, plus the
    existing TOPIC-MAP.md (if any) as context, then asks Claude to organize
    concepts into 5-10 parent research topics. Overwrites TOPIC-MAP.md.

    Unlike ``build_topic_map_scaffold`` in ``index_builder``, which only groups
    concepts by a pre-existing ``parent_topic`` frontmatter field and refuses
    to overwrite, this function produces a structured LLM-written map that
    reflects the current concept graph as a whole. It is intended to be called
    after ``compile_batch_v2`` so the topic hierarchy stays in sync with the
    evolving wiki.

    Returns the path to the written TOPIC-MAP.md.
    """
    from scripts.index_builder import parse_frontmatter

    concepts_dir = wiki_dir / "concepts"
    if not concepts_dir.is_dir():
        logger.warning("No concepts directory at %s, skipping topic map rebuild", concepts_dir)
        topic_map_path = wiki_dir / "TOPIC-MAP.md"
        topic_map_path.write_text(
            "# Topic Map\n\n> No concepts found yet.\n", encoding="utf-8"
        )
        return topic_map_path

    # 1. Collect concept summaries: slug, name, short description
    concept_entries: list[dict] = []
    for md_file in sorted(concepts_dir.glob("*.md")):
        if md_file.name == "INDEX.md":
            continue
        content = md_file.read_text(encoding="utf-8")
        fm = parse_frontmatter(content) or {}
        name = fm.get("concept") or md_file.stem.replace("-", " ").title()
        # Grab the first non-empty paragraph after frontmatter as a description hint
        body = re.sub(r"^---\s*\n.*?\n---\s*\n", "", content, count=1, flags=re.DOTALL)
        body = body.strip()
        # Take up to 300 chars of the first prose block
        first_block = ""
        for block in body.split("\n\n"):
            cleaned = block.strip()
            if cleaned and not cleaned.startswith("#"):
                first_block = cleaned[:300]
                break
        concept_entries.append(
            {
                "slug": md_file.stem,
                "name": str(name),
                "hint": first_block,
            }
        )

    if not concept_entries:
        topic_map_path = wiki_dir / "TOPIC-MAP.md"
        topic_map_path.write_text(
            "# Topic Map\n\n> No concept pages found yet.\n", encoding="utf-8"
        )
        logger.info("TOPIC-MAP.md written as empty (no concepts)")
        return topic_map_path

    # 2. Current topic map as context (may not exist on first run)
    topic_map_path = wiki_dir / "TOPIC-MAP.md"
    current_topic_map = ""
    if topic_map_path.exists():
        current_topic_map = topic_map_path.read_text(encoding="utf-8")[:3000]

    # 3. Build concept list for prompt
    concept_lines = []
    for entry in concept_entries:
        hint = entry["hint"].replace("\n", " ") if entry["hint"] else ""
        if hint:
            concept_lines.append(f"- `{entry['slug']}` ({entry['name']}): {hint}")
        else:
            concept_lines.append(f"- `{entry['slug']}` ({entry['name']})")
    concepts_block = "\n".join(concept_lines)

    existing_block = ""
    if current_topic_map:
        existing_block = (
            "\n\n### 现有 TOPIC-MAP.md（仅供参考，可自由重组）\n\n"
            "```markdown\n"
            f"{current_topic_map}\n"
            "```\n"
        )

    prompt = f"""你是一位机器人学习领域的研究主题整理专家。请根据下面的 concept 列表，把它们组织成一份层次化的研究主题地图（TOPIC-MAP.md）。

## 输入：concept 列表（共 {len(concept_entries)} 个）

{concepts_block}
{existing_block}

## 任务

把这些 concept 归类到 **5-10 个父主题**（parent topics）下，形成 Markdown 大纲。要求：

1. **覆盖率**：列表中的每个 concept 都必须出现在某个父主题下（不要漏掉任何一个）
2. **父主题命名**：使用简洁的英文名（如 "Policy Architectures"、"Force & Contact Control"、"Sim-to-Real"、"Sensing Modalities"、"Teleoperation & Data Collection"）
3. **结构**：父主题用 `## ` 二级标题，子条目用 `- [[slug]]` 的 wikilink 格式
4. **同级排序**：父主题按研究流程顺序排列（感知 → 表征 → 策略 → 控制 → 部署），子条目在每组内按字母序
5. **去重**：同一 concept 不要出现在多个父主题下，只归到最相关的那一个
6. **顶部加一行说明**：在第一行下方加一条 blockquote 说明这个文件是 LLM 自动维护的

## 输出格式

只输出 Markdown 内容，不要任何解释文字，不要用 ``` 代码块包裹。第一行必须是 `# Topic Map`。

示例结构：

# Topic Map

> Research topic hierarchy. Auto-maintained by `rebuild_topic_map_llm`.

## Policy Architectures
- [[diffusion-policy]]
- [[flow-matching-policy]]

## Force & Contact Control
- [[impedance-control]]
- [[hybrid-force-position-control]]

（按上面的规则为全部 {len(concept_entries)} 个 concept 生成）
"""

    # 4. Call Claude
    logger.info("Calling Claude to rebuild TOPIC-MAP.md (%d concepts)", len(concept_entries))
    raw_output = _call_claude(prompt, timeout=timeout)

    # 5. Strip markdown code fences if present
    fence_match = re.search(r"```(?:markdown|md)?\s*\n(.*?)\n```", raw_output, re.DOTALL)
    if fence_match:
        topic_map_content = fence_match.group(1).strip()
    else:
        topic_map_content = raw_output.strip()

    if not topic_map_content.startswith("# "):
        topic_map_content = "# Topic Map\n\n" + topic_map_content

    # 6. Coverage check: warn (don't fail) on missing slugs
    missing_slugs = [
        entry["slug"]
        for entry in concept_entries
        if f"[[{entry['slug']}]]" not in topic_map_content
    ]
    if missing_slugs:
        logger.warning(
            "rebuild_topic_map_llm: %d concept(s) not placed in topic map: %s",
            len(missing_slugs),
            ", ".join(missing_slugs[:10]) + ("..." if len(missing_slugs) > 10 else ""),
        )

    # 7. Write it out
    topic_map_path.write_text(topic_map_content + "\n", encoding="utf-8")
    logger.info(
        "Rebuilt TOPIC-MAP.md: %d concepts, %d missing, %d bytes",
        len(concept_entries),
        len(missing_slugs),
        len(topic_map_content),
    )
    return topic_map_path


def compile_batch_v2(
    arxiv_ids: list[str],
    wiki_dir: Path = WIKI_DIR,
    max_papers: int = 30,
) -> dict:
    """Batch two-step compilation.

    Returns {papers_compiled, concepts_created, concepts_updated, failed}.
    """
    stats = {
        "papers_compiled": 0,
        "concepts_created": 0,
        "concepts_updated": 0,
        "failed": [],
    }

    for i, arxiv_id in enumerate(arxiv_ids[:max_papers]):
        logger.info("[%d/%d] Compiling %s", i + 1, len(arxiv_ids), arxiv_id)
        try:
            result = compile_paper_v2(arxiv_id, wiki_dir)
            stats["papers_compiled"] += 1
            stats["concepts_created"] += result["concepts_created"]
            stats["concepts_updated"] += result["concepts_updated"]
        except Exception:
            logger.exception("Failed to compile %s", arxiv_id)
            stats["failed"].append(arxiv_id)

        # Rate limit between papers (2 LLM calls each)
        if i < len(arxiv_ids) - 1:
            time.sleep(2)

    # Rebuild indexes
    try:
        build_index_pages(wiki_dir)
    except Exception:
        logger.exception("Failed to build index pages")

    # LLM-rebuild TOPIC-MAP.md to reflect the updated concept graph
    try:
        rebuild_topic_map_llm(wiki_dir)
    except Exception:
        logger.exception("Failed to rebuild topic map via LLM")

    logger.info(
        "V2 batch complete: %d compiled, %d concepts created, %d updated, %d failed",
        stats["papers_compiled"],
        stats["concepts_created"],
        stats["concepts_updated"],
        len(stats["failed"]),
    )
    return stats


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def get_concept_index(wiki_dir: Path = WIKI_DIR) -> list[str]:
    """Return list of concept names from wiki/concepts/ directory.

    Converts filenames back to concept names (reverse of slugify):
    'diffusion-policy.md' -> 'Diffusion Policy'
    """
    concepts_dir = wiki_dir / "concepts"
    if not concepts_dir.is_dir():
        return []

    concepts: list[str] = []
    for md_file in sorted(concepts_dir.glob("*.md")):
        # Convert filename to concept name
        name = md_file.stem.replace("-", " ").replace("_", " ")
        # Title case for readability
        name = name.title()
        concepts.append(name)
    return concepts


def lint_wiki(wiki_dir: Path = WIKI_DIR) -> list[str]:
    """Health check: find orphan papers, concepts with no papers, etc.

    Returns list of warning strings.
    """
    warnings: list[str] = []

    papers_dir = wiki_dir / "papers"
    concepts_dir = wiki_dir / "concepts"

    # Check for orphan papers (papers with no concepts linked)
    if papers_dir.is_dir():
        for md_file in papers_dir.glob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            # Check if concepts field is empty in frontmatter
            concepts_field = _extract_frontmatter_field(content, "concepts")
            # Also check if [[concept]] links exist in the body
            has_concept_links = bool(re.search(r"\[\[.+?\]\]", content))
            if (
                not has_concept_links
                and (concepts_field is None or concepts_field == "[]" or concepts_field == "")
            ):
                warnings.append(
                    f"Orphan paper (no concepts): {md_file.name}"
                )

    # Check for empty concept pages
    if concepts_dir.is_dir():
        for md_file in concepts_dir.glob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            # Strip frontmatter and check remaining content
            body = re.sub(r"^---.*?---\s*", "", content, flags=re.DOTALL).strip()
            if len(body) < 10:
                warnings.append(
                    f"Empty concept page: {md_file.name}"
                )

    # Check for potential duplicate concepts (similar slugs)
    if concepts_dir.is_dir():
        concept_files = sorted(concepts_dir.glob("*.md"))
        stems = [f.stem for f in concept_files]
        for i, stem_a in enumerate(stems):
            for stem_b in stems[i + 1:]:
                # Simple similarity: check if one is a prefix of the other
                if stem_a in stem_b or stem_b in stem_a:
                    if stem_a != stem_b:
                        warnings.append(
                            f"Potential duplicate concepts: {stem_a}.md and {stem_b}.md"
                        )

    return warnings
