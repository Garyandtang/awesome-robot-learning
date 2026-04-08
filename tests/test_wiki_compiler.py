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

def test_build_index_pages_creates_readme(tmp_path):
    papers_dir = tmp_path / "papers"
    papers_dir.mkdir(parents=True)
    (papers_dir / "2604.12345.md").write_text("---\ntitle: Test\n---\n# Test")
    concepts_dir = tmp_path / "concepts"
    concepts_dir.mkdir(parents=True)
    (concepts_dir / "diffusion-policy.md").write_text("# DP")
    build_index_pages(wiki_dir=tmp_path)
    readme = tmp_path / "README.md"
    assert readme.exists()

def test_lint_wiki_detects_orphan_papers(tmp_path):
    papers_dir = tmp_path / "papers"
    papers_dir.mkdir(parents=True)
    (papers_dir / "2604.99999.md").write_text("---\ntitle: Orphan\nconcepts: []\n---\n# No concepts")
    concepts_dir = tmp_path / "concepts"
    concepts_dir.mkdir(parents=True)
    warnings = lint_wiki(wiki_dir=tmp_path)
    assert any("concept" in w.lower() or "orphan" in w.lower() for w in warnings)
