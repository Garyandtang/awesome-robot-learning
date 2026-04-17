# tests/test_wiki_compiler.py

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, call
from scripts.wiki_compiler import (
    _slugify,
    _build_paper_prompt,
    _build_concept_extraction_prompt,
    _build_concept_creation_prompt,
    _build_concept_update_prompt,
    compile_paper_page,
    extract_concepts_llm,
    create_concept_page,
    update_concept_page,
    build_index_pages,
    get_concept_index,
    lint_wiki,
)


def _make_paper(**kwargs):
    base = {
        "title": "Diffusion Policy for Robot Manipulation",
        "abstract": "We propose a diffusion-based policy for manipulation.",
        "authors": ["Alice", "Bob"],
        "arxiv_id": "2604.12345",
        "url": "https://arxiv.org/abs/2604.12345",
        "venue": "arXiv",
        "date": "2026.04",
    }
    base.update(kwargs)
    return base


# === Slugify Tests ===

def test_slugify_basic():
    assert _slugify("Diffusion Policy") == "diffusion-policy"

def test_slugify_with_special_chars():
    assert _slugify("Sim-to-Real Transfer") == "sim-to-real-transfer"

def test_slugify_strips_extra_spaces():
    assert _slugify("  Whole  Body  Control  ") == "whole-body-control"


# === Prompt Tests ===

def test_paper_prompt_contains_title():
    prompt = _build_paper_prompt(_make_paper(), [])
    assert "Diffusion Policy for Robot Manipulation" in prompt

def test_paper_prompt_contains_existing_concepts():
    prompt = _build_paper_prompt(_make_paper(), ["Sim-to-Real Transfer", "RL from Human Feedback"])
    assert "Sim-to-Real Transfer" in prompt
    assert "RL from Human Feedback" in prompt

def test_paper_prompt_uses_fulltext_when_available():
    paper = {**_make_paper(), "_fulltext": "This is the full paper content with details."}
    prompt = _build_paper_prompt(paper, [])
    assert "论文全文" in prompt
    assert "full paper content" in prompt
    # Should NOT contain "- 摘要:" content block (fulltext replaces it)
    assert "- 摘要:" not in prompt

def test_paper_prompt_falls_back_to_abstract():
    paper = _make_paper()
    prompt = _build_paper_prompt(paper, [])
    assert "- 摘要:" in prompt
    assert "论文全文" not in prompt

def test_concept_extraction_prompt_lists_existing():
    prompt = _build_concept_extraction_prompt(_make_paper(), ["Diffusion Policy"])
    assert "Diffusion Policy" in prompt
    assert "JSON" in prompt

def test_concept_creation_prompt_contains_concept_name():
    prompt = _build_concept_creation_prompt("Diffusion Policy", _make_paper())
    assert "Diffusion Policy" in prompt
    assert "中文" in prompt

def test_concept_update_prompt_contains_existing_content():
    existing = "# Diffusion Policy\n\n这是一种生成式策略方法。"
    prompt = _build_concept_update_prompt("Diffusion Policy", existing, _make_paper())
    assert "这是一种生成式策略方法" in prompt
    assert _make_paper()["title"] in prompt


# === LLM-Calling Tests (mocked) ===

@patch("scripts.wiki_compiler._call_claude")
def test_compile_paper_page_writes_file(mock_claude, tmp_path):
    mock_claude.return_value = """---
title: "Test Paper"
arxiv_id: "2604.12345"
---
# 核心方法
这是一篇关于扩散策略的论文。"""
    paper = _make_paper()
    result = compile_paper_page(paper, wiki_dir=tmp_path)
    assert result.exists()
    assert result.name == "2604.12345.md"
    content = result.read_text()
    assert "扩散策略" in content

@patch("scripts.wiki_compiler._call_claude")
def test_extract_concepts_llm_returns_list(mock_claude, tmp_path):
    mock_claude.return_value = '["Diffusion Policy", "Robot Manipulation", "Imitation Learning"]'
    concepts = extract_concepts_llm(_make_paper(), wiki_dir=tmp_path)
    assert len(concepts) == 3
    assert "Diffusion Policy" in concepts

@patch("scripts.wiki_compiler._call_claude")
def test_extract_concepts_llm_handles_wrapped_json(mock_claude, tmp_path):
    mock_claude.return_value = '```json\n["Diffusion Policy"]\n```'
    concepts = extract_concepts_llm(_make_paper(), wiki_dir=tmp_path)
    assert concepts == ["Diffusion Policy"]

@patch("scripts.wiki_compiler._call_claude")
def test_create_concept_page_writes_file(mock_claude, tmp_path):
    mock_claude.return_value = """---
concept: "Diffusion Policy"
created: "2026-04-08"
papers:
  - "2604.12345"
---
# Diffusion Policy

扩散策略是一种基于扩散模型的策略学习方法。"""
    result = create_concept_page("Diffusion Policy", _make_paper(), wiki_dir=tmp_path)
    assert result.exists()
    assert result.name == "diffusion-policy.md"

@patch("scripts.wiki_compiler._call_claude")
def test_update_concept_page_preserves_and_extends(mock_claude, tmp_path):
    concepts_dir = tmp_path / "concepts"
    concepts_dir.mkdir(parents=True)
    existing = concepts_dir / "diffusion-policy.md"
    existing.write_text("---\nconcept: Diffusion Policy\npapers:\n  - '2604.00001'\n---\n# 原始内容\n")

    mock_claude.return_value = """---
concept: "Diffusion Policy"
papers:
  - "2604.00001"
  - "2604.12345"
---
# 更新后的内容
包含了新论文的信息。"""

    new_paper = _make_paper(arxiv_id="2604.12345")
    result = update_concept_page("Diffusion Policy", new_paper, wiki_dir=tmp_path)
    content = result.read_text()
    assert "2604.12345" in content
    assert "2604.00001" in content


# === Index and Utility Tests ===

def test_get_concept_index_from_directory(tmp_path):
    concepts_dir = tmp_path / "concepts"
    concepts_dir.mkdir(parents=True)
    (concepts_dir / "diffusion-policy.md").write_text("# Diffusion Policy")
    (concepts_dir / "sim-to-real-transfer.md").write_text("# Sim-to-Real")
    index = get_concept_index(wiki_dir=tmp_path)
    assert len(index) == 2

def test_build_index_pages_creates_canonical_indexes(tmp_path):
    papers_dir = tmp_path / "papers"
    papers_dir.mkdir(parents=True)
    (papers_dir / "2604.12345.md").write_text("---\ntitle: Test\n---\n# Test")
    concepts_dir = tmp_path / "concepts"
    concepts_dir.mkdir(parents=True)
    (concepts_dir / "diffusion-policy.md").write_text("# DP")
    build_index_pages(wiki_dir=tmp_path)
    assert (tmp_path / "INDEX.md").exists()
    assert (tmp_path / "papers" / "INDEX.md").exists()
    assert (tmp_path / "concepts" / "INDEX.md").exists()

def test_lint_wiki_detects_orphan_papers(tmp_path):
    papers_dir = tmp_path / "papers"
    papers_dir.mkdir(parents=True)
    (papers_dir / "2604.99999.md").write_text("---\ntitle: Orphan\nconcepts: []\n---\n# No concepts")
    concepts_dir = tmp_path / "concepts"
    concepts_dir.mkdir(parents=True)
    warnings = lint_wiki(wiki_dir=tmp_path)
    assert any("concept" in w.lower() or "orphan" in w.lower() for w in warnings)


# === V2 Two-Step Compiler Tests ===

from scripts.wiki_compiler import (
    _build_step1_prompt,
    _build_step2_prompt,
    _format_aliases_for_prompt,
    _load_concept_aliases,
    _parse_step1_output,
    _parse_step2_output,
    compile_paper_v2,
    rebuild_topic_map_llm,
)

SAMPLE_RAW_CONTENT = {
    "meta": {
        "id": "2411.15753",
        "type": "paper",
        "title": "FoAR: Force-Aware Reactive Policy",
        "authors": ["Alice", "Bob"],
        "date": "2024.11",
        "venue": "arXiv",
        "url": "https://arxiv.org/abs/2411.15753",
        "abstract": "We propose a force-aware policy...",
    },
    "fulltext": "This is a long paper about force-aware reactive policy..." * 100,
    "repo_readme": "# FoAR\nForce-Aware Reactive Policy implementation.",
}


class TestBuildStep1Prompt:
    def test_includes_raw_content(self):
        prompt = _build_step1_prompt(SAMPLE_RAW_CONTENT, "", "")
        assert "FoAR" in prompt
        assert "Force-Aware" in prompt
        assert "force-aware reactive policy" in prompt

    def test_includes_repo_readme(self):
        prompt = _build_step1_prompt(SAMPLE_RAW_CONTENT, "", "")
        assert "Repo README" in prompt
        assert "FoAR" in prompt

    def test_handles_empty_index(self):
        prompt = _build_step1_prompt(SAMPLE_RAW_CONTENT, "", "")
        assert "尚无概念" in prompt
        assert "尚无主题地图" in prompt

    def test_includes_existing_index(self):
        index = "| [[Diffusion Policy]] | 12 | 扩散策略 |"
        prompt = _build_step1_prompt(SAMPLE_RAW_CONTENT, index, "")
        assert "Diffusion Policy" in prompt

    def test_truncates_fulltext(self):
        long_content = {
            **SAMPLE_RAW_CONTENT,
            "fulltext": "x" * 100_000,
        }
        prompt = _build_step1_prompt(long_content, "", "")
        # Should be truncated to ~60K
        assert len(prompt) < 80_000

    def test_aliases_block_default_empty(self):
        """Backward compat: omitting aliases_block should not inject the section."""
        prompt = _build_step1_prompt(SAMPLE_RAW_CONTENT, "", "")
        assert "概念规范化" not in prompt
        assert "canonical names" not in prompt

    def test_aliases_block_injected_when_provided(self):
        block = (
            "\n### 概念规范化（canonical names）\n\n"
            "- **vla** ← Vision-Language-Action, VLA\n"
            "- **pi-zero** ← pi-0, π₀\n"
        )
        prompt = _build_step1_prompt(SAMPLE_RAW_CONTENT, "", "", aliases_block=block)
        assert "概念规范化" in prompt
        assert "**vla**" in prompt
        assert "Vision-Language-Action" in prompt
        assert "pi-zero" in prompt


class TestConceptAliases:
    def test_load_concept_aliases_returns_empty_when_missing(self, tmp_path: Path):
        # wiki/concepts/ exists but no _aliases.yaml file
        (tmp_path / "concepts").mkdir()
        assert _load_concept_aliases(tmp_path) == {}

    def test_load_concept_aliases_returns_empty_when_concepts_dir_missing(
        self, tmp_path: Path
    ):
        assert _load_concept_aliases(tmp_path) == {}

    def test_load_concept_aliases_reads_yaml(self, tmp_path: Path):
        (tmp_path / "concepts").mkdir()
        (tmp_path / "concepts" / "_aliases.yaml").write_text(
            "vla:\n  - Vision-Language-Action\n  - VLA\n"
            "pi-zero:\n  - pi-0\n  - \"\\u03c0\\u2080\"\n",
            encoding="utf-8",
        )
        result = _load_concept_aliases(tmp_path)
        assert result == {
            "vla": ["Vision-Language-Action", "VLA"],
            "pi-zero": ["pi-0", "π₀"],
        }

    def test_load_concept_aliases_handles_malformed_yaml(self, tmp_path: Path):
        (tmp_path / "concepts").mkdir()
        (tmp_path / "concepts" / "_aliases.yaml").write_text(
            "vla: [unclosed\n", encoding="utf-8"
        )
        assert _load_concept_aliases(tmp_path) == {}

    def test_load_concept_aliases_handles_non_dict_root(self, tmp_path: Path):
        (tmp_path / "concepts").mkdir()
        (tmp_path / "concepts" / "_aliases.yaml").write_text(
            "- item1\n- item2\n", encoding="utf-8"
        )
        assert _load_concept_aliases(tmp_path) == {}

    def test_load_concept_aliases_coerces_none_values(self, tmp_path: Path):
        (tmp_path / "concepts").mkdir()
        (tmp_path / "concepts" / "_aliases.yaml").write_text(
            "vla:\npi-zero:\n  - pi-0\n", encoding="utf-8"
        )
        result = _load_concept_aliases(tmp_path)
        assert result == {"vla": [], "pi-zero": ["pi-0"]}

    def test_format_aliases_empty_returns_empty_string(self):
        assert _format_aliases_for_prompt({}) == ""

    def test_format_aliases_produces_bullet_list(self):
        block = _format_aliases_for_prompt(
            {
                "vla": ["Vision-Language-Action", "VLA"],
                "diffusion-policy": ["Diffusion Policy", "DP"],
            }
        )
        assert "概念规范化" in block
        assert "**vla**" in block
        assert "Vision-Language-Action" in block
        assert "VLA" in block
        assert "**diffusion-policy**" in block
        assert "Diffusion Policy" in block

    def test_format_aliases_sorts_canonicals_alphabetically(self):
        block = _format_aliases_for_prompt(
            {"zulu": ["z1"], "alpha": ["a1"], "mike": ["m1"]}
        )
        assert block.index("alpha") < block.index("mike") < block.index("zulu")

    def test_format_aliases_handles_canonical_without_aliases(self):
        block = _format_aliases_for_prompt({"vla": []})
        assert "**vla**" in block
        # No arrow when alias list is empty
        assert "**vla** ←" not in block


class TestBuildStep2Prompt:
    def test_includes_concept_pages(self):
        fm = {"title": "Test", "concepts": [{"name": "DP", "relation": "uses"}]}
        prompt = _build_step2_prompt(
            fm, "body preview", {"DP": "# Diffusion Policy\ncontent"}, [],
        )
        assert "Diffusion Policy" in prompt
        assert "body preview" in prompt

    def test_includes_new_concepts(self):
        fm = {"title": "Test"}
        new = [{"name": "Force Alignment", "suggested_topic": "Perception", "description": "力对齐"}]
        prompt = _build_step2_prompt(fm, "preview", {}, new)
        assert "Force Alignment" in prompt
        assert "力对齐" in prompt


class TestParseStep1Output:
    def test_extracts_frontmatter_and_body(self):
        output = """---
title: "FoAR"
arxiv_id: "2411.15753"
summary: "力感知策略"
concepts:
  - name: "Force Control"
    relation: "introduces"
    detail: "引入力感知"
new_concepts: []
---

# 深度分析

这篇论文提出了一种力感知策略。"""
        parsed = _parse_step1_output(output)
        assert parsed["frontmatter"]["title"] == "FoAR"
        assert parsed["frontmatter"]["summary"] == "力感知策略"
        assert "深度分析" in parsed["body"]

    def test_raises_on_no_frontmatter(self):
        with pytest.raises(ValueError, match="no YAML"):
            _parse_step1_output("No frontmatter here")

    def test_raises_on_invalid_yaml(self):
        with pytest.raises(ValueError, match="Invalid YAML"):
            _parse_step1_output("---\n: invalid: yaml: [[\n---\nbody")

    def test_tolerates_leading_preamble(self):
        """LLM sometimes prepends explanatory text before the frontmatter."""
        output = """好的，我来分析这篇论文。

---
title: "FoAR"
summary: "力感知策略"
---

# 深度分析

内容。"""
        parsed = _parse_step1_output(output)
        assert parsed["frontmatter"]["title"] == "FoAR"
        assert "深度分析" in parsed["body"]

    def test_tolerates_markdown_code_fence(self):
        """LLM sometimes wraps the whole output in a ```markdown fence."""
        output = """```markdown
---
title: "FoAR"
summary: "力感知策略"
---

# 深度分析

内容。
```"""
        parsed = _parse_step1_output(output)
        assert parsed["frontmatter"]["title"] == "FoAR"
        assert "深度分析" in parsed["body"]

    def test_tolerates_md_code_fence(self):
        """Also accepts ```md variant of the fence."""
        output = """```md
---
title: "FoAR"
---
# Body"""
        # No closing fence — fallback regex should still find the frontmatter
        parsed = _parse_step1_output(output)
        assert parsed["frontmatter"]["title"] == "FoAR"

    def test_tolerates_nested_fence_inside_frontmatter_delimiters(self):
        """Real failure mode: Claude wraps YAML in ```markdown INSIDE --- delimiters.

        Observed output:
            ---

            ```markdown
            title: ForceVLA
            summary: ...
            ```

            ---
            body
        """
        output = """---

```markdown
title: "ForceVLA"
summary: "力感知 MoE"
---

# 深度分析

正文内容。
```"""
        parsed = _parse_step1_output(output)
        assert parsed["frontmatter"]["title"] == "ForceVLA"
        assert "深度分析" in parsed["body"]

    def test_skips_invalid_first_candidate(self):
        """If the first ---...--- block is not valid YAML, try the next one."""
        output = """一些开场白。

---
这不是 YAML，只是 markdown 分隔线。
---

---
title: "Real"
summary: "真正的 frontmatter"
---

# Body"""
        parsed = _parse_step1_output(output)
        assert parsed["frontmatter"]["title"] == "Real"

    def test_skips_candidate_without_title(self):
        """Frontmatter must have a title field to be accepted."""
        output = """---
not_title: "x"
---

---
title: "Real"
---
body"""
        parsed = _parse_step1_output(output)
        assert parsed["frontmatter"]["title"] == "Real"


class TestParseStep2Output:
    def test_splits_concepts(self):
        output = """===CONCEPT: Force Control===
---
concept: "Force Control"
---
# Force Control
Content here.

===NEW_CONCEPT: Force Alignment===
---
concept: "Force Alignment"
---
# Force Alignment
New concept content."""
        results = _parse_step2_output(output)
        assert len(results) == 2
        assert results[0]["name"] == "Force Control"
        assert results[0]["is_new"] is False
        assert results[1]["name"] == "Force Alignment"
        assert results[1]["is_new"] is True

    def test_handles_empty_output(self):
        assert _parse_step2_output("") == []
        assert _parse_step2_output("no delimiters here") == []

    def test_strips_outer_markdown_code_fence(self):
        """LLM sometimes wraps the entire response in ```markdown ... ```."""
        output = """```markdown
===CONCEPT: Force Control===
---
concept: "Force Control"
---
# Force Control
Content here.
```"""
        results = _parse_step2_output(output)
        assert len(results) == 1
        assert results[0]["name"] == "Force Control"
        # The trailing ``` must not leak into concept content
        assert "```" not in results[0]["content"]

    def test_strips_per_concept_code_fence(self):
        """Each concept block may be individually wrapped in a code fence."""
        output = """===CONCEPT: Force Control===
```markdown
---
concept: "Force Control"
---
# Force Control
Content.
```

===CONCEPT: Impedance Control===
```
---
concept: "Impedance Control"
---
# Impedance Control
More content.
```"""
        results = _parse_step2_output(output)
        assert len(results) == 2
        for r in results:
            assert "```" not in r["content"]
            assert r["content"].startswith("---")

    def test_skips_empty_concept_name(self):
        """`===CONCEPT:  ===` must not produce a `.md` garbage file."""
        output = """===CONCEPT:  ===
some orphan content

===CONCEPT: Real Concept===
---
concept: "Real Concept"
---
# Real Concept
valid content"""
        results = _parse_step2_output(output)
        assert len(results) == 1
        assert results[0]["name"] == "Real Concept"


class TestCompilePaperV2:
    @patch("scripts.wiki_compiler._call_claude")
    def test_end_to_end(self, mock_claude, tmp_path):
        # Setup raw layer
        raw_dir = tmp_path / "raw" / "papers" / "2411.15753"
        raw_dir.mkdir(parents=True)
        import yaml
        meta = {
            "id": "2411.15753",
            "title": "FoAR",
            "authors": ["Alice"],
            "date": "2024.11",
            "venue": "arXiv",
            "url": "https://arxiv.org/abs/2411.15753",
            "compile_status": {"compiled_at": None, "wiki_page": None, "stale": True},
        }
        (raw_dir / "meta.yaml").write_text(yaml.dump(meta, allow_unicode=True))
        (raw_dir / "fulltext.md").write_text("Full text of the paper...")

        # Mock Step 1 output
        step1 = """---
title: "FoAR"
arxiv_id: "2411.15753"
summary: "力感知反应策略"
concepts:
  - name: "Force Control"
    relation: "introduces"
    detail: "引入力感知"
new_concepts:
  - name: "Force Alignment"
    suggested_topic: "Perception"
    description: "力对齐"
---

# 分析

这篇论文提出了力感知反应策略。"""

        # Mock Step 2 output
        step2 = """===NEW_CONCEPT: Force Control===
---
concept: "Force Control"
created: "2026-04-09"
updated: "2026-04-09"
papers:
  - "2411.15753"
description: "力控制方法"
---
# Force Control
力控制概念页。

===NEW_CONCEPT: Force Alignment===
---
concept: "Force Alignment"
created: "2026-04-09"
updated: "2026-04-09"
papers:
  - "2411.15753"
description: "力对齐"
---
# Force Alignment
力对齐概念页。"""

        mock_claude.side_effect = [step1, step2]

        result = compile_paper_v2("2411.15753", wiki_dir=tmp_path)

        # Verify paper page written
        assert result["paper_page"].exists()
        assert "FoAR" in result["paper_page"].read_text()

        # Verify concept pages created
        assert (tmp_path / "concepts" / "force-control.md").exists()
        assert (tmp_path / "concepts" / "force-alignment.md").exists()
        assert result["concepts_created"] == 2

        # Verify meta.yaml updated
        updated_meta = yaml.safe_load((raw_dir / "meta.yaml").read_text())
        assert updated_meta["compile_status"]["stale"] is False


# === rebuild_topic_map_llm Tests ===


class TestRebuildTopicMapLLM:
    def _make_concept(self, wiki_dir: Path, slug: str, name: str, body_hint: str = ""):
        concepts_dir = wiki_dir / "concepts"
        concepts_dir.mkdir(parents=True, exist_ok=True)
        fm = f'---\nconcept: "{name}"\n---\n\n# {name}\n\n{body_hint}\n'
        (concepts_dir / f"{slug}.md").write_text(fm, encoding="utf-8")

    def test_writes_placeholder_when_no_concepts_dir(self, tmp_path: Path):
        path = rebuild_topic_map_llm(wiki_dir=tmp_path)
        assert path.exists()
        assert path.name == "TOPIC-MAP.md"
        content = path.read_text(encoding="utf-8")
        assert "Topic Map" in content
        assert "No concepts" in content

    def test_writes_placeholder_when_concepts_dir_empty(self, tmp_path: Path):
        (tmp_path / "concepts").mkdir()
        (tmp_path / "concepts" / "INDEX.md").write_text("# INDEX\n")
        path = rebuild_topic_map_llm(wiki_dir=tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "Topic Map" in content
        assert "No concept" in content

    @patch("scripts.wiki_compiler._call_claude")
    def test_calls_llm_with_concept_list(self, mock_claude, tmp_path: Path):
        self._make_concept(tmp_path, "diffusion-policy", "Diffusion Policy", "A DDPM-based policy.")
        self._make_concept(tmp_path, "impedance-control", "Impedance Control", "Cartesian impedance.")
        mock_claude.return_value = (
            "# Topic Map\n\n"
            "> Auto-maintained.\n\n"
            "## Policy Architectures\n- [[diffusion-policy]]\n\n"
            "## Force & Contact Control\n- [[impedance-control]]\n"
        )

        path = rebuild_topic_map_llm(wiki_dir=tmp_path)

        mock_claude.assert_called_once()
        prompt = mock_claude.call_args[0][0]
        assert "diffusion-policy" in prompt
        assert "Diffusion Policy" in prompt
        assert "A DDPM-based policy" in prompt
        assert "impedance-control" in prompt
        assert "共 2 个" in prompt

        content = path.read_text(encoding="utf-8")
        assert "# Topic Map" in content
        assert "[[diffusion-policy]]" in content
        assert "[[impedance-control]]" in content

    @patch("scripts.wiki_compiler._call_claude")
    def test_strips_markdown_code_fences(self, mock_claude, tmp_path: Path):
        self._make_concept(tmp_path, "vla", "VLA")
        mock_claude.return_value = (
            "```markdown\n"
            "# Topic Map\n\n## Policy\n- [[vla]]\n"
            "```"
        )

        path = rebuild_topic_map_llm(wiki_dir=tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "```" not in content
        assert content.startswith("# Topic Map")
        assert "[[vla]]" in content

    @patch("scripts.wiki_compiler._call_claude")
    def test_prepends_header_when_missing(self, mock_claude, tmp_path: Path):
        self._make_concept(tmp_path, "vla", "VLA")
        mock_claude.return_value = "## Policy\n- [[vla]]"

        path = rebuild_topic_map_llm(wiki_dir=tmp_path)
        content = path.read_text(encoding="utf-8")
        assert content.startswith("# Topic Map")
        assert "[[vla]]" in content

    @patch("scripts.wiki_compiler._call_claude")
    def test_warns_on_missing_slugs_but_still_writes(self, mock_claude, tmp_path: Path, caplog):
        self._make_concept(tmp_path, "alpha", "Alpha")
        self._make_concept(tmp_path, "beta", "Beta")
        self._make_concept(tmp_path, "gamma", "Gamma")
        # LLM only places alpha and beta, drops gamma
        mock_claude.return_value = (
            "# Topic Map\n\n## Group\n- [[alpha]]\n- [[beta]]\n"
        )

        import logging
        with caplog.at_level(logging.WARNING, logger="scripts.wiki_compiler"):
            path = rebuild_topic_map_llm(wiki_dir=tmp_path)

        # File still written
        content = path.read_text(encoding="utf-8")
        assert "[[alpha]]" in content
        assert "[[beta]]" in content
        # Warning emitted about missing
        assert any("gamma" in rec.message for rec in caplog.records)

    @patch("scripts.wiki_compiler._call_claude")
    def test_overwrites_existing_topic_map(self, mock_claude, tmp_path: Path):
        self._make_concept(tmp_path, "vla", "VLA")
        (tmp_path / "TOPIC-MAP.md").write_text("# Old Topic Map\n\nobsolete content\n")
        mock_claude.return_value = "# Topic Map\n\n## New Group\n- [[vla]]\n"

        path = rebuild_topic_map_llm(wiki_dir=tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "obsolete content" not in content
        assert "New Group" in content
        # Prompt should have included the old topic map as context
        prompt = mock_claude.call_args[0][0]
        assert "现有 TOPIC-MAP.md" in prompt
        assert "Old Topic Map" in prompt

    @patch("scripts.wiki_compiler._call_claude")
    def test_skips_index_md_from_concept_list(self, mock_claude, tmp_path: Path):
        self._make_concept(tmp_path, "vla", "VLA")
        (tmp_path / "concepts" / "INDEX.md").write_text("# Concepts INDEX\n")
        mock_claude.return_value = "# Topic Map\n\n## Policy\n- [[vla]]\n"

        rebuild_topic_map_llm(wiki_dir=tmp_path)
        prompt = mock_claude.call_args[0][0]
        assert "共 1 个" in prompt
        assert "`INDEX`" not in prompt
