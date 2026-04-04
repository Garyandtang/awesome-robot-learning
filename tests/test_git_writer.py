import pytest
from scripts.git_writer import format_entry, find_section_range, insert_entry


SAMPLE_README = """\
# Awesome-Robot-Learning

## Manipulation
- [arXiv 2026.03](https://arxiv.org/abs/2603.00100), Paper Alpha
- [arXiv 2026.01](https://arxiv.org/abs/2601.00050), Paper Beta

## Loco-Manipulation

## VLA (Vision-Language-Action)
- [arXiv 2026.02](https://arxiv.org/abs/2602.00200), Paper Gamma

## Force Control & Perception

## Sim-to-Real

## System & Foundation Model

## Hardware

---

## Contact
"""


def test_format_entry_basic():
    paper = {
        "venue": "arXiv",
        "date": "2026.04",
        "url": "https://arxiv.org/abs/2604.00001",
        "title": "Test Paper",
        "has_code": False,
        "project_url": None,
    }
    result = format_entry(paper)
    assert result == "- [arXiv 2026.04](https://arxiv.org/abs/2604.00001), Test Paper"


def test_format_entry_with_code_and_website():
    paper = {
        "venue": "arXiv",
        "date": "2026.04",
        "url": "https://arxiv.org/abs/2604.00001",
        "title": "Test Paper",
        "has_code": True,
        "project_url": "https://test.github.io",
    }
    result = format_entry(paper)
    assert result == "- 🌟 [arXiv 2026.04](https://arxiv.org/abs/2604.00001), Test Paper, [website](https://test.github.io)"


def test_find_section_range():
    lines = SAMPLE_README.split("\n")
    start, end = find_section_range(lines, "Manipulation")
    assert lines[start].startswith("## Manipulation")
    # Should end before the next section
    assert lines[end].startswith("## Loco-Manipulation")


def test_find_section_range_vla():
    lines = SAMPLE_README.split("\n")
    start, end = find_section_range(lines, "VLA")
    assert "VLA" in lines[start]


def test_insert_entry_newest_first():
    paper = {
        "venue": "arXiv",
        "date": "2026.02",
        "url": "https://arxiv.org/abs/2602.00500",
        "title": "New Paper",
        "has_code": False,
        "project_url": None,
        "arxiv_id": "2602.00500",
    }
    result = insert_entry(SAMPLE_README, paper, "Manipulation")
    lines = result.split("\n")
    # New paper (2026.02) should be between Alpha (2026.03) and Beta (2026.01)
    alpha_idx = next(i for i, l in enumerate(lines) if "Paper Alpha" in l)
    new_idx = next(i for i, l in enumerate(lines) if "New Paper" in l)
    beta_idx = next(i for i, l in enumerate(lines) if "Paper Beta" in l)
    assert alpha_idx < new_idx < beta_idx


def test_insert_entry_empty_section():
    paper = {
        "venue": "arXiv",
        "date": "2026.04",
        "url": "https://arxiv.org/abs/2604.00001",
        "title": "First Paper",
        "has_code": False,
        "project_url": None,
        "arxiv_id": "2604.00001",
    }
    result = insert_entry(SAMPLE_README, paper, "Loco-Manipulation")
    assert "First Paper" in result
    lines = result.split("\n")
    loco_idx = next(i for i, l in enumerate(lines) if l.startswith("## Loco-Manipulation"))
    first_idx = next(i for i, l in enumerate(lines) if "First Paper" in l)
    assert first_idx == loco_idx + 1
