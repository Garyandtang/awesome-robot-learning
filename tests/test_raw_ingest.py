"""Tests for scripts.raw_ingest module."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from scripts.raw_ingest import (
    _build_meta,
    _fetch_repo_readme,
    _line_is_math_heavy,
    _parse_marker_image_name,
    _rewrite_marker_refs,
    _write_meta_yaml,
    extract_formulas,
    extract_fulltext_and_images_with_marker,
    extract_fulltext_with_latex,
    extract_images,
    ingest_batch,
    ingest_paper,
    load_raw_content,
    load_raw_meta,
    reextract_fulltext,
    reextract_images,
    save_marker_images,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_ARXIV_META = {
    "title": "Force-Aware Reactive Policy",
    "authors": ["Alice", "Bob"],
    "abstract": "We propose...",
    "url": "https://arxiv.org/abs/2411.15753",
    "pdf_url": "https://arxiv.org/pdf/2411.15753",
    "venue": "arXiv",
    "date": "2024.11",
    "arxiv_id": "2411.15753",
    "project_url": None,
    "has_code": False,
}

SAMPLE_S2_META = {
    "title": "Force-Aware Reactive Policy",
    "authors": ["Alice", "Bob"],
    "abstract": "We propose...",
    "url": "https://arxiv.org/abs/2411.15753",
    "pdf_url": "",
    "venue": "arXiv",
    "date": "2024",
    "arxiv_id": "2411.15753",
    "project_url": None,
    "has_code": True,
}


# ---------------------------------------------------------------------------
# _build_meta
# ---------------------------------------------------------------------------


class TestBuildMeta:
    def test_merges_fields(self) -> None:
        meta = _build_meta(SAMPLE_ARXIV_META, SAMPLE_S2_META, ["fulltext.md"])
        assert meta["id"] == "2411.15753"
        assert meta["type"] == "paper"
        assert meta["title"] == "Force-Aware Reactive Policy"
        assert meta["authors"] == ["Alice", "Bob"]
        assert meta["assets"] == ["fulltext.md"]

    def test_defaults_compile_status_stale(self) -> None:
        meta = _build_meta(SAMPLE_ARXIV_META, None, [])
        assert meta["compile_status"]["stale"] is True
        assert meta["compile_status"]["compiled_at"] is None
        assert meta["compile_status"]["wiki_page"] is None

    def test_has_code_from_s2(self) -> None:
        meta = _build_meta(SAMPLE_ARXIV_META, SAMPLE_S2_META, [])
        assert meta["has_code"] is True

    def test_has_code_false_without_s2(self) -> None:
        meta = _build_meta(SAMPLE_ARXIV_META, None, [])
        assert meta["has_code"] is False

    def test_sets_dates(self) -> None:
        meta = _build_meta(SAMPLE_ARXIV_META, None, [])
        today = date.today().isoformat()
        assert meta["fetched_at"] == today
        assert meta["updated_at"] == today


# ---------------------------------------------------------------------------
# _write_meta_yaml
# ---------------------------------------------------------------------------


class TestWriteMetaYaml:
    def test_creates_file(self, tmp_path: Path) -> None:
        meta = {"id": "test", "title": "Test Paper"}
        path = _write_meta_yaml(tmp_path, meta)
        assert path.exists()
        loaded = yaml.safe_load(path.read_text())
        assert loaded["id"] == "test"
        assert loaded["title"] == "Test Paper"


# ---------------------------------------------------------------------------
# _fetch_repo_readme
# ---------------------------------------------------------------------------


class TestFetchRepoReadme:
    def test_returns_none_for_empty_url(self) -> None:
        assert _fetch_repo_readme("") is None
        assert _fetch_repo_readme(None) is None

    def test_returns_none_for_non_github(self) -> None:
        assert _fetch_repo_readme("https://gitlab.com/foo/bar") is None

    @patch("scripts.raw_ingest.requests.get")
    def test_fetches_main_branch(self, mock_get) -> None:
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "# Repo README\n" + "content " * 50
        result = _fetch_repo_readme("https://github.com/owner/repo")
        assert result is not None
        assert "Repo README" in result
        # Should try main branch first
        call_url = mock_get.call_args_list[0][0][0]
        assert "/main/" in call_url


# ---------------------------------------------------------------------------
# ingest_paper
# ---------------------------------------------------------------------------


class TestIngestPaper:
    @patch("scripts.raw_ingest.fetch_fulltext", return_value="Full paper text here..." * 100)
    @patch("scripts.raw_ingest.fetch_s2_metadata", return_value=None)
    @patch("scripts.raw_ingest.fetch_arxiv_metadata", return_value=SAMPLE_ARXIV_META)
    def test_creates_directory_structure(
        self, mock_arxiv, mock_s2, mock_ft, tmp_path: Path
    ) -> None:
        paper_dir = ingest_paper("2411.15753", tmp_path)

        assert paper_dir == tmp_path / "raw/papers/2411.15753"
        assert (paper_dir / "meta.yaml").exists()
        assert (paper_dir / "fulltext.md").exists()

        meta = yaml.safe_load((paper_dir / "meta.yaml").read_text())
        assert meta["id"] == "2411.15753"
        assert "fulltext.md" in meta["assets"]

    @patch("scripts.raw_ingest._fetch_pdf_bytes", return_value=None)
    @patch("scripts.raw_ingest.fetch_fulltext", return_value=None)
    @patch("scripts.raw_ingest.fetch_s2_metadata", return_value=None)
    @patch("scripts.raw_ingest.fetch_arxiv_metadata", return_value=SAMPLE_ARXIV_META)
    def test_handles_no_fulltext(
        self, mock_arxiv, mock_s2, mock_ft, mock_pdf, tmp_path: Path
    ) -> None:
        paper_dir = ingest_paper("2411.15753", tmp_path)
        assert not (paper_dir / "fulltext.md").exists()
        meta = yaml.safe_load((paper_dir / "meta.yaml").read_text())
        assert "fulltext.md" not in meta["assets"]

    @patch("scripts.raw_ingest.fetch_fulltext", return_value="text")
    @patch("scripts.raw_ingest.fetch_s2_metadata", return_value=None)
    @patch("scripts.raw_ingest.fetch_arxiv_metadata", return_value=SAMPLE_ARXIV_META)
    def test_idempotent_skips_existing(
        self, mock_arxiv, mock_s2, mock_ft, tmp_path: Path
    ) -> None:
        # First ingest
        ingest_paper("2411.15753", tmp_path)
        mock_arxiv.reset_mock()

        # Second ingest should skip
        ingest_paper("2411.15753", tmp_path)
        mock_arxiv.assert_not_called()

    @patch("scripts.raw_ingest.fetch_fulltext", return_value="text")
    @patch("scripts.raw_ingest.fetch_s2_metadata", return_value=None)
    @patch("scripts.raw_ingest.fetch_arxiv_metadata", return_value=SAMPLE_ARXIV_META)
    def test_force_reingests(
        self, mock_arxiv, mock_s2, mock_ft, tmp_path: Path
    ) -> None:
        ingest_paper("2411.15753", tmp_path)
        mock_arxiv.reset_mock()

        ingest_paper("2411.15753", tmp_path, force=True)
        mock_arxiv.assert_called_once()

    @patch("scripts.raw_ingest.fetch_arxiv_metadata", return_value=None)
    def test_raises_on_missing_metadata(self, mock_arxiv, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Failed to fetch"):
            ingest_paper("9999.99999", tmp_path)


# ---------------------------------------------------------------------------
# ingest_batch
# ---------------------------------------------------------------------------


class TestIngestBatch:
    @patch("scripts.raw_ingest.fetch_fulltext", return_value="text")
    @patch("scripts.raw_ingest.fetch_s2_metadata", return_value=None)
    @patch("scripts.raw_ingest.fetch_arxiv_metadata", return_value=SAMPLE_ARXIV_META)
    def test_tracks_stats(
        self, mock_arxiv, mock_s2, mock_ft, tmp_path: Path
    ) -> None:
        result = ingest_batch(["2411.15753", "2411.15753"], tmp_path, delay=0)
        assert result["ingested"] == 1
        assert result["skipped"] == 1
        assert result["failed"] == []

    @patch("scripts.raw_ingest.fetch_arxiv_metadata", return_value=None)
    def test_tracks_failures(self, mock_arxiv, tmp_path: Path) -> None:
        result = ingest_batch(["bad.id"], tmp_path, delay=0)
        assert result["failed"] == ["bad.id"]
        assert result["ingested"] == 0


# ---------------------------------------------------------------------------
# load_raw_content
# ---------------------------------------------------------------------------


class TestLoadRawContent:
    def test_loads_all_fields(self, tmp_path: Path) -> None:
        paper_dir = tmp_path / "raw/papers/2411.15753"
        paper_dir.mkdir(parents=True)

        meta = {"id": "2411.15753", "title": "Test"}
        _write_meta_yaml(paper_dir, meta)
        (paper_dir / "fulltext.md").write_text("Full text content")
        (paper_dir / "repo-readme.md").write_text("# README")

        content = load_raw_content("2411.15753", tmp_path)
        assert content["meta"]["id"] == "2411.15753"
        assert content["fulltext"] == "Full text content"
        assert content["repo_readme"] == "# README"

    def test_handles_missing_optional_files(self, tmp_path: Path) -> None:
        paper_dir = tmp_path / "raw/papers/2411.15753"
        paper_dir.mkdir(parents=True)

        meta = {"id": "2411.15753", "title": "Test"}
        _write_meta_yaml(paper_dir, meta)

        content = load_raw_content("2411.15753", tmp_path)
        assert content["fulltext"] is None
        assert content["repo_readme"] is None

    def test_raises_on_missing_dir(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_raw_content("nonexistent", tmp_path)


# ---------------------------------------------------------------------------
# load_raw_meta
# ---------------------------------------------------------------------------


class TestLoadRawMeta:
    def test_loads_meta(self, tmp_path: Path) -> None:
        paper_dir = tmp_path / "raw/papers/2411.15753"
        paper_dir.mkdir(parents=True)
        meta = {"id": "2411.15753", "title": "Test"}
        _write_meta_yaml(paper_dir, meta)

        loaded = load_raw_meta("2411.15753", tmp_path)
        assert loaded["id"] == "2411.15753"

    def test_returns_none_for_missing(self, tmp_path: Path) -> None:
        assert load_raw_meta("nonexistent", tmp_path) is None


# ---------------------------------------------------------------------------
# extract_images
# ---------------------------------------------------------------------------


def _build_fixture_pdf(num_images: int = 2, with_formulas: bool = False) -> bytes:
    """Build a tiny in-memory PDF with embedded images (and optional formulas)."""
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.Document()
    page = doc.new_page()

    # Embed ``num_images`` distinct pixmaps so each gets a unique xref.
    for i in range(num_images):
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40 + i, 40 + i))
        pix.clear_with(32 + i * 20)
        rect = pymupdf.Rect(50 + i * 60, 50, 90 + i * 60, 90)
        page.insert_image(rect, pixmap=pix)

    if with_formulas:
        # Plain-text math-heavy lines the heuristic should catch.
        formula_lines = (
            "L = α ∑ (y_i - ŷ_i)^2 + β ||θ||^2\n"
            "p(x|y) ∝ exp(−‖x − μ‖^2 / σ^2)\n"
            "∂L/∂θ = 2α ∑ (y_i − ŷ_i) ∇_θ ŷ_i\n"
        )
        page.insert_text((50, 200), formula_lines, fontsize=10)

    data = doc.tobytes()
    doc.close()
    return data


class TestExtractImages:
    def test_extracts_manifest(self, tmp_path: Path) -> None:
        pytest.importorskip("pymupdf")
        pdf = _build_fixture_pdf(num_images=2)
        out_dir = tmp_path / "images"

        manifest = extract_images(pdf, out_dir)

        assert len(manifest) == 2
        for entry in manifest:
            assert entry["page"] == 1
            assert entry["path"].startswith("images/")
            assert entry["width"] >= 32
            assert entry["height"] >= 32
            assert entry["ext"] in {"png", "jpeg", "jpg"}
            assert entry["bytes"] > 0
            full = tmp_path / entry["path"]
            assert full.exists()
            assert full.stat().st_size == entry["bytes"]

    def test_skips_tiny_images(self, tmp_path: Path) -> None:
        pymupdf = pytest.importorskip("pymupdf")
        doc = pymupdf.Document()
        page = doc.new_page()
        tiny = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8))
        tiny.clear_with(200)
        page.insert_image(pymupdf.Rect(10, 10, 20, 20), pixmap=tiny)
        pdf = doc.tobytes()
        doc.close()

        manifest = extract_images(pdf, tmp_path / "images")
        assert manifest == []

    def test_handles_bad_pdf(self, tmp_path: Path) -> None:
        manifest = extract_images(b"not a pdf", tmp_path / "images")
        assert manifest == []


# ---------------------------------------------------------------------------
# extract_formulas
# ---------------------------------------------------------------------------


class TestLineIsMathHeavy:
    def test_detects_greek_and_operators(self) -> None:
        assert _line_is_math_heavy("L = α ∑ (y_i - ŷ_i)^2")

    def test_rejects_plain_prose(self) -> None:
        assert not _line_is_math_heavy(
            "This paper proposes a novel method for force-aware manipulation."
        )

    def test_rejects_too_short(self) -> None:
        assert not _line_is_math_heavy("α")

    def test_rejects_too_long(self) -> None:
        long = "α " * 200
        assert not _line_is_math_heavy(long)


class TestExtractFormulas:
    def test_returns_markdown_for_math_heavy_pdf(self, monkeypatch) -> None:
        """Test the formula pipeline end-to-end, stubbing get_text to avoid the
        fact that PyMuPDF's builtin fonts cannot render Unicode math glyphs
        after a round-trip through ``insert_text``."""
        pytest.importorskip("pymupdf")
        pdf = _build_fixture_pdf(num_images=0, with_formulas=False)

        fake_text = (
            "Some prose that should be ignored entirely.\n"
            "L = α ∑ (y_i - ŷ_i)^2 + β ||θ||^2\n"
            "p(x|y) ∝ exp(−‖x − μ‖^2 / σ^2)\n"
            "∂L/∂θ = 2α ∑ (y_i − ŷ_i) ∇_θ ŷ_i\n"
        )

        import pymupdf as _pymupdf

        real_open = _pymupdf.open

        class _StubPage:
            def get_text(self, *args, **kwargs):
                return fake_text

        class _StubDoc:
            def __init__(self, real):
                self._real = real

            def __iter__(self):
                # Yield one stub page per real page so the real close() still works.
                for _ in self._real:
                    yield _StubPage()

            def close(self):
                self._real.close()

        def fake_open(*args, **kwargs):
            return _StubDoc(real_open(*args, **kwargs))

        # extract_formulas re-imports pymupdf inside the function, so patching
        # the pymupdf module itself works for both call sites.
        import pymupdf
        monkeypatch.setattr(pymupdf, "open", fake_open)

        result = extract_formulas(pdf)
        assert result is not None
        assert "Page 1" in result
        assert "α" in result and "∑" in result

    def test_returns_none_for_low_signal_pdf(self) -> None:
        pymupdf = pytest.importorskip("pymupdf")
        doc = pymupdf.Document()
        page = doc.new_page()
        page.insert_text((50, 50), "Hello world. No math here.", fontsize=12)
        pdf = doc.tobytes()
        doc.close()
        assert extract_formulas(pdf) is None

    def test_handles_bad_pdf(self) -> None:
        assert extract_formulas(b"not a pdf") is None


# ---------------------------------------------------------------------------
# ingest_paper image/formula integration
# ---------------------------------------------------------------------------


class TestIngestPaperWithAssets:
    @patch("scripts.raw_ingest.fetch_fulltext", return_value="Full paper text here..." * 100)
    @patch("scripts.raw_ingest.fetch_s2_metadata", return_value=None)
    @patch("scripts.raw_ingest.fetch_arxiv_metadata", return_value=SAMPLE_ARXIV_META)
    def test_writes_images_manifest(
        self, mock_arxiv, mock_s2, mock_ft, tmp_path: Path
    ) -> None:
        pytest.importorskip("pymupdf")
        pdf = _build_fixture_pdf(num_images=2)
        with patch("scripts.raw_ingest._fetch_pdf_bytes", return_value=pdf):
            paper_dir = ingest_paper("2411.15753", tmp_path)

        manifest_path = paper_dir / "images.json"
        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text())
        assert "images" in data
        assert len(data["images"]) == 2
        assert (paper_dir / "images").is_dir()
        meta = yaml.safe_load((paper_dir / "meta.yaml").read_text())
        assert "images.json" in meta["assets"]

    @patch("scripts.raw_ingest.fetch_fulltext", return_value="text")
    @patch("scripts.raw_ingest.fetch_s2_metadata", return_value=None)
    @patch("scripts.raw_ingest.fetch_arxiv_metadata", return_value=SAMPLE_ARXIV_META)
    def test_skips_asset_extraction_when_already_present(
        self, mock_arxiv, mock_s2, mock_ft, tmp_path: Path
    ) -> None:
        pytest.importorskip("pymupdf")
        pdf = _build_fixture_pdf(num_images=1)
        with patch("scripts.raw_ingest._fetch_pdf_bytes", return_value=pdf) as mock_pdf:
            ingest_paper("2411.15753", tmp_path)
            assert mock_pdf.call_count == 1
            # Second call (non-forced) should skip PDF fetch entirely.
            ingest_paper("2411.15753", tmp_path)
            assert mock_pdf.call_count == 1

    @patch("scripts.raw_ingest.fetch_fulltext", return_value="text")
    @patch("scripts.raw_ingest.fetch_s2_metadata", return_value=None)
    @patch("scripts.raw_ingest.fetch_arxiv_metadata", return_value=SAMPLE_ARXIV_META)
    def test_force_reruns_asset_extraction(
        self, mock_arxiv, mock_s2, mock_ft, tmp_path: Path
    ) -> None:
        pytest.importorskip("pymupdf")
        pdf = _build_fixture_pdf(num_images=1)
        with patch("scripts.raw_ingest._fetch_pdf_bytes", return_value=pdf) as mock_pdf:
            ingest_paper("2411.15753", tmp_path)
            ingest_paper("2411.15753", tmp_path, force=True)
            assert mock_pdf.call_count == 2


# ---------------------------------------------------------------------------
# extract_fulltext_with_latex + reextract_fulltext (Marker pipeline)
# ---------------------------------------------------------------------------


class TestExtractFulltextWithLatex:
    """Marker is mocked so these tests run in milliseconds and have no GPU deps."""

    def test_returns_none_when_marker_missing(self, tmp_path: Path) -> None:
        """If marker-pdf isn't importable, the function degrades to None."""
        with patch(
            "scripts.raw_ingest._get_marker_converter", return_value=None
        ):
            result = extract_fulltext_with_latex(b"%PDF-1.4")
        assert result is None

    def test_returns_none_for_empty_bytes(self) -> None:
        assert extract_fulltext_with_latex(b"") is None

    def test_uses_injected_converter_and_returns_markdown(
        self, tmp_path: Path
    ) -> None:
        """When a converter is passed in, it is called with a PDF path and
        the rendered output is piped through ``text_from_rendered``."""
        from unittest.mock import MagicMock

        fake_rendered = object()
        fake_converter = MagicMock(return_value=fake_rendered)

        with patch(
            "marker.output.text_from_rendered",
            return_value=("# Title\n\n$E=mc^2$\n", None, None),
        ) as mock_text:
            result = extract_fulltext_with_latex(
                b"%PDF-1.4 fake bytes", converter=fake_converter
            )

        assert result == "# Title\n\n$E=mc^2$\n"
        # The converter was called exactly once with a temp file path (str).
        assert fake_converter.call_count == 1
        (call_path,) = fake_converter.call_args.args
        assert isinstance(call_path, str)
        assert call_path.endswith(".pdf")
        mock_text.assert_called_once_with(fake_rendered)

    def test_returns_none_on_converter_exception(self) -> None:
        from unittest.mock import MagicMock

        fake_converter = MagicMock(side_effect=RuntimeError("marker boom"))
        result = extract_fulltext_with_latex(
            b"%PDF-1.4 fake", converter=fake_converter
        )
        assert result is None


class TestReextractFulltext:
    def _seed_paper(self, tmp_path: Path, arxiv_id: str = "2411.15753") -> Path:
        paper_dir = tmp_path / "raw" / "papers" / arxiv_id
        paper_dir.mkdir(parents=True)
        meta = {
            "id": arxiv_id,
            "type": "paper",
            "title": "FoAR",
            "authors": ["Alice"],
            "date": "2024.11",
            "venue": "arXiv",
            "url": f"https://arxiv.org/abs/{arxiv_id}",
            "assets": ["fulltext.md"],
        }
        (paper_dir / "meta.yaml").write_text(yaml.dump(meta), encoding="utf-8")
        (paper_dir / "fulltext.md").write_text("old text without formulas\n", encoding="utf-8")
        return paper_dir

    def test_skips_when_no_meta_yaml(self, tmp_path: Path) -> None:
        result = reextract_fulltext("0000.00000", tmp_path)
        assert result["status"] == "skipped"

    def test_fails_when_pdf_download_fails(self, tmp_path: Path) -> None:
        self._seed_paper(tmp_path)
        with patch("scripts.raw_ingest._fetch_pdf_bytes", return_value=None):
            result = reextract_fulltext("2411.15753", tmp_path)
        assert result["status"] == "failed"
        assert "pdf" in result["reason"].lower()

    def test_overwrites_fulltext_on_success(self, tmp_path: Path) -> None:
        paper_dir = self._seed_paper(tmp_path)
        new_md = "# FoAR\n\nContact-rich policy. $p_t \\in \\mathbb{R}^{6}$.\n"
        with (
            patch("scripts.raw_ingest._fetch_pdf_bytes", return_value=b"%PDF"),
            patch(
                "scripts.raw_ingest.extract_fulltext_with_latex", return_value=new_md
            ),
        ):
            result = reextract_fulltext("2411.15753", tmp_path)
        assert result["status"] == "ok"
        assert result["chars"] == len(new_md)
        assert result["formulas"] >= 1
        assert (paper_dir / "fulltext.md").read_text() == new_md

    def test_updates_meta_assets_and_date(self, tmp_path: Path) -> None:
        paper_dir = self._seed_paper(tmp_path)
        # Start with an assets list that is missing fulltext.md.
        meta = yaml.safe_load((paper_dir / "meta.yaml").read_text())
        meta["assets"] = []
        (paper_dir / "meta.yaml").write_text(yaml.dump(meta), encoding="utf-8")

        with (
            patch("scripts.raw_ingest._fetch_pdf_bytes", return_value=b"%PDF"),
            patch(
                "scripts.raw_ingest.extract_fulltext_with_latex",
                return_value="body\n",
            ),
        ):
            reextract_fulltext("2411.15753", tmp_path)

        updated = yaml.safe_load((paper_dir / "meta.yaml").read_text())
        assert "fulltext.md" in updated["assets"]
        assert updated["updated_at"] == date.today().isoformat()

    def test_counts_block_and_inline_formulas(self, tmp_path: Path) -> None:
        self._seed_paper(tmp_path)
        md = (
            "Intro prose.\n\n"
            "Inline formula $a + b = c$ here.\n\n"
            "$$\n\\sum_{i=0}^{N} x_i\n$$\n\n"
            "Another inline $E = mc^2$.\n"
        )
        with (
            patch("scripts.raw_ingest._fetch_pdf_bytes", return_value=b"%PDF"),
            patch("scripts.raw_ingest.extract_fulltext_with_latex", return_value=md),
        ):
            result = reextract_fulltext("2411.15753", tmp_path)
        # 1 block ($$...$$) + 2 inline ($...$, $...$) = 3 formulas.
        assert result["formulas"] == 3


# ---------------------------------------------------------------------------
# Marker image extraction helpers
# ---------------------------------------------------------------------------


class _FakePILImage:
    """Lightweight stand-in for PIL.Image to avoid pulling Pillow into the
    unit-test mock stack. Implements the tiny surface area ``save_marker_images``
    needs: ``width``, ``height``, ``mode``, ``save(buf, format=...)``, ``convert``."""

    def __init__(self, width: int = 100, height: int = 80, mode: str = "RGB") -> None:
        self.width = width
        self.height = height
        self.mode = mode

    def save(self, buf, format: str = "JPEG") -> None:  # noqa: A002 - mimic PIL
        # Write deterministic bytes so tests can assert bytes > 0.
        buf.write(f"FAKE:{format}:{self.width}x{self.height}".encode())

    def convert(self, mode: str) -> "_FakePILImage":
        return _FakePILImage(self.width, self.height, mode)


class TestParseMarkerImageName:
    def test_parses_figure(self) -> None:
        assert _parse_marker_image_name("_page_0_Figure_11.jpeg") == (1, 11, "jpeg")

    def test_parses_picture(self) -> None:
        assert _parse_marker_image_name("_page_5_Picture_0.png") == (6, 0, "png")

    def test_parses_table(self) -> None:
        assert _parse_marker_image_name("_page_2_Table_3.jpeg") == (3, 3, "jpeg")

    def test_returns_none_for_garbage(self) -> None:
        assert _parse_marker_image_name("random.png") is None
        assert _parse_marker_image_name("_page_X_Figure_0.png") is None


class TestRewriteMarkerRefs:
    def test_rewrites_known_ref(self) -> None:
        md = "Intro ![](_page_0_Figure_0.jpeg) caption"
        rewritten = _rewrite_marker_refs(
            md, {"_page_0_Figure_0.jpeg": "images/page001-img00.jpeg"}
        )
        assert rewritten == "Intro ![](images/page001-img00.jpeg) caption"

    def test_drops_orphaned_ref(self) -> None:
        md = "Text ![](_page_0_Figure_9.jpeg) more"
        rewritten = _rewrite_marker_refs(md, {"_page_0_Figure_9.jpeg": ""})
        assert "![](" not in rewritten
        assert "Text  more" in rewritten

    def test_preserves_unrelated_refs(self) -> None:
        md = "![logo](https://cdn/logo.png) and ![](_page_0_Figure_0.jpeg)"
        rewritten = _rewrite_marker_refs(
            md, {"_page_0_Figure_0.jpeg": "images/page001-img00.jpeg"}
        )
        assert "![logo](https://cdn/logo.png)" in rewritten
        assert "images/page001-img00.jpeg" in rewritten


class TestSaveMarkerImages:
    def test_writes_manifest_and_files(self, tmp_path: Path) -> None:
        images = {
            "_page_0_Figure_0.jpeg": _FakePILImage(640, 480),
            "_page_2_Picture_3.png": _FakePILImage(200, 150, mode="RGB"),
        }
        md = "A ![](_page_0_Figure_0.jpeg) and B ![](_page_2_Picture_3.png)."
        manifest, rewritten = save_marker_images(images, tmp_path / "images", markdown=md)

        assert len(manifest) == 2
        for entry in manifest:
            assert entry["path"].startswith("images/")
            assert entry["width"] >= 32
            assert entry["height"] >= 32
            assert entry["bytes"] > 0
        # Files were actually written to disk.
        for entry in manifest:
            assert (tmp_path / entry["path"]).exists()
        # Markdown refs were rewritten to the new paths.
        assert "images/page001-img00.jpeg" in rewritten
        assert "images/page003-img03.png" in rewritten
        assert "_page_0_Figure_0.jpeg" not in rewritten

    def test_drops_tiny_images(self, tmp_path: Path) -> None:
        images = {
            "_page_0_Figure_0.jpeg": _FakePILImage(10, 10),  # under _MIN_IMAGE_DIM
        }
        md = "X ![](_page_0_Figure_0.jpeg) Y"
        manifest, rewritten = save_marker_images(images, tmp_path / "images", markdown=md)
        assert manifest == []
        assert "![](" not in rewritten

    def test_drops_unparseable_names(self, tmp_path: Path) -> None:
        images = {"random.png": _FakePILImage()}
        md = "![](random.png)"
        manifest, rewritten = save_marker_images(images, tmp_path / "images", markdown=md)
        assert manifest == []
        # Unparseable ref is still stripped so nothing 404s later.
        assert "![](" not in rewritten

    def test_manifest_sorted_by_page_then_index(self, tmp_path: Path) -> None:
        images = {
            "_page_5_Figure_2.jpeg": _FakePILImage(),
            "_page_0_Figure_0.jpeg": _FakePILImage(),
            "_page_5_Figure_0.jpeg": _FakePILImage(),
        }
        manifest, _ = save_marker_images(images, tmp_path / "images", markdown="")
        pages_indices = [(m["page"], m["index"]) for m in manifest]
        assert pages_indices == [(1, 0), (6, 0), (6, 2)]


class TestExtractFulltextAndImagesWithMarker:
    def test_returns_none_without_converter(self) -> None:
        with patch("scripts.raw_ingest._get_marker_converter", return_value=None):
            assert extract_fulltext_and_images_with_marker(b"%PDF-1.4") is None

    def test_returns_none_for_empty_bytes(self) -> None:
        assert extract_fulltext_and_images_with_marker(b"") is None

    def test_returns_markdown_and_images(self) -> None:
        from unittest.mock import MagicMock

        fake_rendered = object()
        fake_converter = MagicMock(return_value=fake_rendered)
        fake_images = {"_page_0_Figure_0.jpeg": _FakePILImage()}

        with patch(
            "marker.output.text_from_rendered",
            return_value=("body with ![](_page_0_Figure_0.jpeg)", "md", fake_images),
        ):
            result = extract_fulltext_and_images_with_marker(
                b"%PDF-1.4 fake", converter=fake_converter
            )

        assert result is not None
        md, imgs = result
        assert "![](_page_0_Figure_0.jpeg)" in md
        assert imgs == fake_images

    def test_returns_none_on_converter_exception(self) -> None:
        from unittest.mock import MagicMock

        fake_converter = MagicMock(side_effect=RuntimeError("boom"))
        result = extract_fulltext_and_images_with_marker(
            b"%PDF-1.4", converter=fake_converter
        )
        assert result is None


class TestReextractImages:
    def _seed_paper(self, tmp_path: Path, arxiv_id: str = "2411.15753") -> Path:
        paper_dir = tmp_path / "raw" / "papers" / arxiv_id
        paper_dir.mkdir(parents=True)
        meta = {
            "id": arxiv_id,
            "type": "paper",
            "title": "Test",
            "authors": ["Alice"],
            "assets": ["fulltext.md"],
        }
        (paper_dir / "meta.yaml").write_text(yaml.dump(meta), encoding="utf-8")
        (paper_dir / "fulltext.md").write_text("placeholder\n", encoding="utf-8")
        return paper_dir

    def test_skipped_without_meta(self, tmp_path: Path) -> None:
        result = reextract_images("0000.00000", tmp_path)
        assert result["status"] == "skipped"
        assert result["images"] == 0

    def test_failed_when_pdf_download_fails(self, tmp_path: Path) -> None:
        self._seed_paper(tmp_path)
        with patch("scripts.raw_ingest._fetch_pdf_bytes", return_value=None):
            result = reextract_images("2411.15753", tmp_path)
        assert result["status"] == "failed"

    def test_failed_when_marker_returns_none(self, tmp_path: Path) -> None:
        self._seed_paper(tmp_path)
        with (
            patch("scripts.raw_ingest._fetch_pdf_bytes", return_value=b"%PDF"),
            patch(
                "scripts.raw_ingest.extract_fulltext_and_images_with_marker",
                return_value=None,
            ),
        ):
            result = reextract_images("2411.15753", tmp_path)
        assert result["status"] == "failed"

    def test_writes_images_and_rewrites_fulltext(self, tmp_path: Path) -> None:
        paper_dir = self._seed_paper(tmp_path)
        md_in = (
            "# Title\n\n"
            "Intro with inline formula $E=mc^2$.\n\n"
            "![](_page_0_Figure_0.jpeg)\n\n"
            "Figure 1 caption.\n"
        )
        raw_imgs = {"_page_0_Figure_0.jpeg": _FakePILImage(640, 480)}

        with (
            patch("scripts.raw_ingest._fetch_pdf_bytes", return_value=b"%PDF"),
            patch(
                "scripts.raw_ingest.extract_fulltext_and_images_with_marker",
                return_value=(md_in, raw_imgs),
            ),
        ):
            result = reextract_images("2411.15753", tmp_path)

        assert result["status"] == "ok"
        assert result["images"] == 1
        assert result["refs"] == 1
        # LaTeX formulas preserved.
        ft = (paper_dir / "fulltext.md").read_text()
        assert "$E=mc^2$" in ft
        # Image ref rewritten to local path.
        assert "![](images/page001-img00.jpeg)" in ft
        # Image file + manifest exist.
        assert (paper_dir / "images" / "page001-img00.jpeg").exists()
        manifest = json.loads((paper_dir / "images.json").read_text())
        assert len(manifest["images"]) == 1

    def test_updates_meta_assets(self, tmp_path: Path) -> None:
        paper_dir = self._seed_paper(tmp_path)
        with (
            patch("scripts.raw_ingest._fetch_pdf_bytes", return_value=b"%PDF"),
            patch(
                "scripts.raw_ingest.extract_fulltext_and_images_with_marker",
                return_value=("body", {}),
            ),
        ):
            reextract_images("2411.15753", tmp_path)

        meta = yaml.safe_load((paper_dir / "meta.yaml").read_text())
        assets = set(meta["assets"])
        assert {"fulltext.md", "images.json", "images/"}.issubset(assets)
        assert meta["updated_at"] == date.today().isoformat()

    def test_does_not_mutate_existing_non_marker_image_refs(self, tmp_path: Path) -> None:
        self._seed_paper(tmp_path)
        md_in = "![logo](https://cdn/logo.png) text"
        with (
            patch("scripts.raw_ingest._fetch_pdf_bytes", return_value=b"%PDF"),
            patch(
                "scripts.raw_ingest.extract_fulltext_and_images_with_marker",
                return_value=(md_in, {}),
            ),
        ):
            result = reextract_images("2411.15753", tmp_path)
        assert result["status"] == "ok"
        ft = (tmp_path / "raw" / "papers" / "2411.15753" / "fulltext.md").read_text()
        assert "![logo](https://cdn/logo.png)" in ft
