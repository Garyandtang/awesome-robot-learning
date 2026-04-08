"""LLM-compiled research wiki following Karpathy's method."""

from __future__ import annotations

import json
import logging
import re
import subprocess
import time
from datetime import date
from pathlib import Path

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


# ---------------------------------------------------------------------------
# Prompt builders (THE HEART OF KARPATHY'S METHOD)
# ---------------------------------------------------------------------------


def _build_paper_prompt(paper: dict, existing_concepts: list[str]) -> str:
    """Build prompt for paper page."""
    concepts_context = ""
    if existing_concepts:
        concepts_context = f"""
以下是知识库中已有的研究概念，如果这篇论文与其中某些概念相关，请在分析中建立联系：
{chr(10).join(f'- {c}' for c in existing_concepts[:30])}
"""
    return f"""你是一个机器人学习领域的研究助手。请为以下论文撰写一篇深度分析文章（中文）。

## 论文信息
- 标题: {paper['title']}
- 作者: {', '.join(paper.get('authors', ['未知']))}
- 发表: {paper.get('venue', '未知')} {paper.get('date', '')}
- 链接: {paper.get('url', '')}
- 摘要: {paper.get('abstract', '无摘要')}
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

    Returns path to the written .md file.
    """
    papers_dir = wiki_dir / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)

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
    """Rebuild README and category pages."""
    build_wiki_readme(wiki_dir)

    # Build category indexes from paper frontmatter
    categories_dir = wiki_dir / "categories"
    categories_dir.mkdir(parents=True, exist_ok=True)

    # Scan papers for category/venue info
    categories: dict[str, list[dict]] = {}
    papers_dir = wiki_dir / "papers"
    if papers_dir.is_dir():
        for md_file in sorted(papers_dir.glob("*.md")):
            content = md_file.read_text(encoding="utf-8")
            # Extract venue from frontmatter
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
