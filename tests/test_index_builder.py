"""Tests for scripts.index_builder module."""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts.index_builder import (
    build_all_indexes,
    build_concept_index,
    build_global_index,
    build_paper_index,
    build_topic_map_scaffold,
    parse_frontmatter,
)


# ---------------------------------------------------------------------------
# parse_frontmatter
# ---------------------------------------------------------------------------


class TestParseFrontmatter:
    def test_parses_valid_yaml(self) -> None:
        content = "---\ntitle: Test Paper\ndate: '2024.11'\n---\n# Body"
        fm = parse_frontmatter(content)
        assert fm is not None
        assert fm["title"] == "Test Paper"
        assert fm["date"] == "2024.11"

    def test_returns_none_for_no_frontmatter(self) -> None:
        assert parse_frontmatter("# No frontmatter here") is None

    def test_returns_none_for_invalid_yaml(self) -> None:
        assert parse_frontmatter("---\n: invalid: [[\n---\nbody") is None

    def test_returns_none_for_non_dict(self) -> None:
        assert parse_frontmatter("---\n- just a list\n---\nbody") is None

    def test_handles_complex_frontmatter(self) -> None:
        content = """---
title: "Test"
concepts:
  - name: "DP"
    relation: "uses"
  - name: "RL"
papers:
  - "2411.00001"
---
# Body"""
        fm = parse_frontmatter(content)
        assert fm is not None
        assert len(fm["concepts"]) == 2
        assert fm["concepts"][0]["name"] == "DP"


# ---------------------------------------------------------------------------
# build_paper_index
# ---------------------------------------------------------------------------


class TestBuildPaperIndex:
    def test_creates_index_file(self, tmp_path: Path) -> None:
        papers_dir = tmp_path / "papers"
        papers_dir.mkdir()
        (papers_dir / "2411.00001.md").write_text(
            "---\ntitle: Paper A\narxiv_id: '2411.00001'\ndate: '2024.11'\nsummary: A summary\nconcepts:\n  - name: RL\n---\n# Body"
        )
        result = build_paper_index(tmp_path)
        assert result == papers_dir / "INDEX.md"
        assert result.exists()

    def test_groups_by_year(self, tmp_path: Path) -> None:
        papers_dir = tmp_path / "papers"
        papers_dir.mkdir()
        (papers_dir / "2024.md").write_text(
            "---\ntitle: Paper 2024\narxiv_id: '2411.00001'\ndate: '2024.11'\n---\n"
        )
        (papers_dir / "2025.md").write_text(
            "---\ntitle: Paper 2025\narxiv_id: '2503.00001'\ndate: '2025.03'\n---\n"
        )
        build_paper_index(tmp_path)
        content = (papers_dir / "INDEX.md").read_text()
        assert "## 2025" in content
        assert "## 2024" in content
        # 2025 should appear before 2024 (reverse order)
        assert content.index("## 2025") < content.index("## 2024")

    def test_counts_total(self, tmp_path: Path) -> None:
        papers_dir = tmp_path / "papers"
        papers_dir.mkdir()
        for i in range(3):
            (papers_dir / f"paper{i}.md").write_text(
                f"---\ntitle: Paper {i}\ndate: '2024.0{i+1}'\n---\n"
            )
        build_paper_index(tmp_path)
        content = (papers_dir / "INDEX.md").read_text()
        assert "3 papers" in content

    def test_skips_index_file(self, tmp_path: Path) -> None:
        papers_dir = tmp_path / "papers"
        papers_dir.mkdir()
        (papers_dir / "INDEX.md").write_text("# Old index")
        (papers_dir / "real.md").write_text("---\ntitle: Real\ndate: '2024.01'\n---\n")
        build_paper_index(tmp_path)
        content = (papers_dir / "INDEX.md").read_text()
        assert "1 papers" in content

    def test_handles_missing_date(self, tmp_path: Path) -> None:
        papers_dir = tmp_path / "papers"
        papers_dir.mkdir()
        (papers_dir / "nodate.md").write_text("---\ntitle: No Date\n---\n")
        build_paper_index(tmp_path)
        content = (papers_dir / "INDEX.md").read_text()
        assert "Unknown" in content

    def test_empty_directory(self, tmp_path: Path) -> None:
        result = build_paper_index(tmp_path)
        assert result.exists()
        content = result.read_text()
        assert "0 papers" in content


# ---------------------------------------------------------------------------
# build_concept_index
# ---------------------------------------------------------------------------


class TestBuildConceptIndex:
    def test_creates_index_file(self, tmp_path: Path) -> None:
        concepts_dir = tmp_path / "concepts"
        concepts_dir.mkdir()
        (concepts_dir / "diffusion-policy.md").write_text(
            "---\nconcept: Diffusion Policy\npapers:\n  - '2411.00001'\ndescription: A generative policy\n---\n"
        )
        result = build_concept_index(tmp_path)
        assert result == concepts_dir / "INDEX.md"
        assert result.exists()
        content = result.read_text()
        assert "Diffusion Policy" in content
        assert "1" in content  # papers count

    def test_alphabetical_sort(self, tmp_path: Path) -> None:
        concepts_dir = tmp_path / "concepts"
        concepts_dir.mkdir()
        (concepts_dir / "rl.md").write_text("---\nconcept: Reinforcement Learning\n---\n")
        (concepts_dir / "dp.md").write_text("---\nconcept: Diffusion Policy\n---\n")
        build_concept_index(tmp_path)
        content = (concepts_dir / "INDEX.md").read_text()
        assert content.index("Diffusion Policy") < content.index("Reinforcement Learning")

    def test_counts_concepts(self, tmp_path: Path) -> None:
        concepts_dir = tmp_path / "concepts"
        concepts_dir.mkdir()
        for name in ["a", "b", "c"]:
            (concepts_dir / f"{name}.md").write_text(f"---\nconcept: {name}\n---\n")
        build_concept_index(tmp_path)
        content = (concepts_dir / "INDEX.md").read_text()
        assert "3 concepts" in content

    def test_skips_index_file(self, tmp_path: Path) -> None:
        concepts_dir = tmp_path / "concepts"
        concepts_dir.mkdir()
        (concepts_dir / "INDEX.md").write_text("# Old")
        (concepts_dir / "real.md").write_text("---\nconcept: Real\n---\n")
        build_concept_index(tmp_path)
        content = (concepts_dir / "INDEX.md").read_text()
        assert "1 concepts" in content

    def test_fallback_name_from_filename(self, tmp_path: Path) -> None:
        concepts_dir = tmp_path / "concepts"
        concepts_dir.mkdir()
        (concepts_dir / "force-control.md").write_text("# No frontmatter")
        build_concept_index(tmp_path)
        content = (concepts_dir / "INDEX.md").read_text()
        assert "Force Control" in content


# ---------------------------------------------------------------------------
# build_global_index
# ---------------------------------------------------------------------------


class TestBuildGlobalIndex:
    def test_creates_index_file(self, tmp_path: Path) -> None:
        result = build_global_index(tmp_path)
        assert result == tmp_path / "INDEX.md"
        assert result.exists()

    def test_includes_stats(self, tmp_path: Path) -> None:
        papers_dir = tmp_path / "papers"
        papers_dir.mkdir()
        (papers_dir / "p1.md").write_text("---\ntitle: P1\n---\n")
        concepts_dir = tmp_path / "concepts"
        concepts_dir.mkdir()
        (concepts_dir / "c1.md").write_text("---\nconcept: C1\n---\n")
        build_global_index(tmp_path)
        content = (tmp_path / "INDEX.md").read_text()
        assert "1 papers" in content
        assert "1 concepts" in content

    def test_includes_navigation(self, tmp_path: Path) -> None:
        build_global_index(tmp_path)
        content = (tmp_path / "INDEX.md").read_text()
        assert "Paper Index" in content
        assert "Concept Index" in content
        assert "Topic Map" in content

    def test_detects_orphan_papers(self, tmp_path: Path) -> None:
        papers_dir = tmp_path / "papers"
        papers_dir.mkdir()
        # Paper with no wiki-links
        (papers_dir / "orphan.md").write_text("---\ntitle: Orphan\n---\n# No links")
        build_global_index(tmp_path)
        content = (tmp_path / "INDEX.md").read_text()
        assert "Orphan papers" in content
        assert ": 1" in content

    def test_detects_stale_papers(self, tmp_path: Path) -> None:
        raw_dir = tmp_path / "raw" / "papers" / "2411.00001"
        raw_dir.mkdir(parents=True)
        meta = {"id": "2411.00001", "compile_status": {"stale": True}}
        (raw_dir / "meta.yaml").write_text(yaml.dump(meta))
        build_global_index(tmp_path)
        content = (tmp_path / "INDEX.md").read_text()
        assert "Stale papers" in content
        assert ": 1" in content


# ---------------------------------------------------------------------------
# build_topic_map_scaffold
# ---------------------------------------------------------------------------


class TestBuildTopicMapScaffold:
    def test_creates_from_concept_parent_topics(self, tmp_path: Path) -> None:
        concepts_dir = tmp_path / "concepts"
        concepts_dir.mkdir()
        (concepts_dir / "dp.md").write_text(
            "---\nconcept: Diffusion Policy\nparent_topic: Policy Learning\n---\n"
        )
        (concepts_dir / "fc.md").write_text(
            "---\nconcept: Force Control\nparent_topic: Perception\n---\n"
        )
        result = build_topic_map_scaffold(tmp_path)
        assert result is not None
        assert result.exists()
        content = result.read_text()
        assert "## Policy Learning" in content
        assert "[[Diffusion Policy]]" in content
        assert "## Perception" in content
        assert "[[Force Control]]" in content

    def test_does_not_overwrite_existing(self, tmp_path: Path) -> None:
        topic_map = tmp_path / "TOPIC-MAP.md"
        topic_map.write_text("# Existing topic map\n## Custom Topic\n")
        result = build_topic_map_scaffold(tmp_path)
        assert result is None
        assert "Custom Topic" in topic_map.read_text()

    def test_includes_new_concepts_from_papers(self, tmp_path: Path) -> None:
        papers_dir = tmp_path / "papers"
        papers_dir.mkdir()
        (papers_dir / "p1.md").write_text(
            "---\ntitle: Test\nnew_concepts:\n  - name: Force Alignment\n    suggested_topic: Perception\n---\n"
        )
        result = build_topic_map_scaffold(tmp_path)
        assert result is not None
        content = result.read_text()
        assert "## Perception" in content
        assert "[[Force Alignment]]" in content

    def test_creates_minimal_scaffold_when_empty(self, tmp_path: Path) -> None:
        result = build_topic_map_scaffold(tmp_path)
        assert result is not None
        content = result.read_text()
        assert "## Uncategorized" in content


# ---------------------------------------------------------------------------
# build_all_indexes
# ---------------------------------------------------------------------------


class TestBuildAllIndexes:
    def test_returns_all_paths(self, tmp_path: Path) -> None:
        result = build_all_indexes(tmp_path)
        assert "paper_index" in result
        assert "concept_index" in result
        assert "global_index" in result
        assert "topic_map" in result
        assert result["paper_index"].exists()
        assert result["concept_index"].exists()
        assert result["global_index"].exists()

    def test_end_to_end(self, tmp_path: Path) -> None:
        # Setup papers and concepts
        papers_dir = tmp_path / "papers"
        papers_dir.mkdir()
        (papers_dir / "2411.00001.md").write_text(
            "---\ntitle: FoAR\narxiv_id: '2411.00001'\ndate: '2024.11'\nconcepts:\n  - name: Force Control\n---\n# Body\n[[Force Control]]"
        )
        concepts_dir = tmp_path / "concepts"
        concepts_dir.mkdir()
        (concepts_dir / "force-control.md").write_text(
            "---\nconcept: Force Control\nparent_topic: Perception\npapers:\n  - '2411.00001'\ndescription: Force-based control\n---\n"
        )

        result = build_all_indexes(tmp_path)

        # Paper index
        pi_content = result["paper_index"].read_text()
        assert "FoAR" in pi_content
        assert "2024" in pi_content

        # Concept index
        ci_content = result["concept_index"].read_text()
        assert "Force Control" in ci_content

        # Global index
        gi_content = result["global_index"].read_text()
        assert "1 papers" in gi_content
        assert "1 concepts" in gi_content

        # Topic map (scaffold created)
        assert result["topic_map"] is not None
        tm_content = result["topic_map"].read_text()
        assert "## Perception" in tm_content
