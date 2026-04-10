"""Tests for scripts.ingest — manual paper ingest CLI."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from scripts.ingest import ingest_and_compile


@pytest.fixture()
def wiki_dir(tmp_path: Path) -> Path:
    """Create a minimal wiki directory with raw data for one paper."""
    raw = tmp_path / "raw" / "papers" / "2411.15753"
    raw.mkdir(parents=True)
    (raw / "meta.yaml").write_text("title: FoAR\ndate: '2024.11'\n")
    return tmp_path


class TestIngestAndCompile:
    """Tests for the ingest_and_compile orchestrator."""

    @patch("scripts.ingest.build_all_indexes")
    @patch("scripts.ingest.compile_paper_v2")
    @patch("scripts.ingest.ingest_paper")
    def test_full_pipeline(self, mock_ingest, mock_compile, mock_indexes, wiki_dir):
        """Ingest + compile + rebuild indexes for a single paper."""
        result = ingest_and_compile(["2411.15753"], wiki_dir)

        mock_ingest.assert_called_once_with("2411.15753", wiki_dir, force=False)
        mock_compile.assert_called_once_with("2411.15753", wiki_dir=wiki_dir)
        mock_indexes.assert_called_once_with(wiki_dir)
        assert result["ingested"] == 1
        assert result["compiled"] == 1
        assert result["failed"] == []

    @patch("scripts.ingest.build_all_indexes")
    @patch("scripts.ingest.compile_paper_v2")
    @patch("scripts.ingest.ingest_paper")
    def test_multiple_papers(self, mock_ingest, mock_compile, mock_indexes, wiki_dir):
        """Process multiple arXiv IDs in sequence."""
        # Create raw data for second paper too
        raw2 = wiki_dir / "raw" / "papers" / "2503.08548"
        raw2.mkdir(parents=True)
        (raw2 / "meta.yaml").write_text("title: TLA\ndate: '2025.03'\n")

        result = ingest_and_compile(["2411.15753", "2503.08548"], wiki_dir)

        assert mock_ingest.call_count == 2
        assert mock_compile.call_count == 2
        assert result["ingested"] == 2
        assert result["compiled"] == 2

    @patch("scripts.ingest.build_all_indexes")
    @patch("scripts.ingest.compile_paper_v2")
    @patch("scripts.ingest.ingest_paper")
    def test_ingest_only(self, mock_ingest, mock_compile, mock_indexes, wiki_dir):
        """With ingest_only, skip compilation and index rebuild."""
        result = ingest_and_compile(["2411.15753"], wiki_dir, ingest_only=True)

        mock_ingest.assert_called_once()
        mock_compile.assert_not_called()
        mock_indexes.assert_not_called()
        assert result["ingested"] == 1
        assert result["compiled"] == 0

    @patch("scripts.ingest.build_all_indexes")
    @patch("scripts.ingest.compile_paper_v2")
    @patch("scripts.ingest.ingest_paper")
    def test_compile_only(self, mock_ingest, mock_compile, mock_indexes, wiki_dir):
        """With compile_only, skip ingestion."""
        result = ingest_and_compile(["2411.15753"], wiki_dir, compile_only=True)

        mock_ingest.assert_not_called()
        mock_compile.assert_called_once()
        mock_indexes.assert_called_once()
        assert result["compiled"] == 1

    @patch("scripts.ingest.build_all_indexes")
    @patch("scripts.ingest.compile_paper_v2")
    @patch("scripts.ingest.ingest_paper")
    def test_compile_only_no_raw_data(self, mock_ingest, mock_compile, mock_indexes, wiki_dir):
        """compile_only with missing raw data should fail gracefully."""
        result = ingest_and_compile(["9999.99999"], wiki_dir, compile_only=True)

        mock_compile.assert_not_called()
        assert result["failed"] == ["9999.99999"]

    @patch("scripts.ingest.build_all_indexes")
    @patch("scripts.ingest.compile_paper_v2")
    @patch("scripts.ingest.ingest_paper")
    def test_force_flag(self, mock_ingest, mock_compile, mock_indexes, wiki_dir):
        """Force flag is passed through to ingest_paper."""
        ingest_and_compile(["2411.15753"], wiki_dir, force=True)

        mock_ingest.assert_called_once_with("2411.15753", wiki_dir, force=True)

    @patch("scripts.ingest.build_all_indexes")
    @patch("scripts.ingest.compile_paper_v2")
    @patch("scripts.ingest.ingest_paper")
    def test_ingest_failure_skips_compile(self, mock_ingest, mock_compile, mock_indexes, wiki_dir):
        """If ingest fails, skip compilation for that paper."""
        mock_ingest.side_effect = RuntimeError("network error")

        result = ingest_and_compile(["2411.15753"], wiki_dir)

        mock_compile.assert_not_called()
        assert result["ingested"] == 0
        assert result["failed"] == ["2411.15753"]

    @patch("scripts.ingest.build_all_indexes")
    @patch("scripts.ingest.compile_paper_v2")
    @patch("scripts.ingest.ingest_paper")
    def test_compile_failure_records_failed(self, mock_ingest, mock_compile, mock_indexes, wiki_dir):
        """If compilation fails, record the paper as failed."""
        mock_compile.side_effect = RuntimeError("LLM error")

        result = ingest_and_compile(["2411.15753"], wiki_dir)

        assert result["ingested"] == 1
        assert result["compiled"] == 0
        assert result["failed"] == ["2411.15753"]

    @patch("scripts.ingest.build_all_indexes")
    @patch("scripts.ingest.compile_paper_v2")
    @patch("scripts.ingest.ingest_paper")
    def test_no_index_rebuild_when_nothing_compiled(self, mock_ingest, mock_compile, mock_indexes, wiki_dir):
        """Index rebuild is skipped when no papers were compiled."""
        mock_compile.side_effect = RuntimeError("LLM error")

        ingest_and_compile(["2411.15753"], wiki_dir)

        mock_indexes.assert_not_called()

    @patch("scripts.ingest.build_all_indexes")
    @patch("scripts.ingest.compile_paper_v2")
    @patch("scripts.ingest.ingest_paper")
    def test_default_wiki_dir(self, mock_ingest, mock_compile, mock_indexes, tmp_path):
        """When wiki_dir is None, resolves via get_wiki_path()."""
        with patch("scripts.ingest.get_wiki_path", return_value=tmp_path):
            raw = tmp_path / "raw" / "papers" / "2411.15753"
            raw.mkdir(parents=True)
            (raw / "meta.yaml").write_text("title: test\n")

            ingest_and_compile(["2411.15753"])

            mock_ingest.assert_called_once_with("2411.15753", tmp_path, force=False)


class TestMain:
    """Tests for the CLI entry point."""

    @patch("scripts.ingest.ingest_and_compile")
    def test_cli_single_id(self, mock_fn):
        """CLI passes a single arXiv ID."""
        mock_fn.return_value = {"ingested": 1, "compiled": 1, "failed": []}
        from scripts.ingest import main

        with patch("sys.argv", ["ingest", "2411.15753"]):
            main()

        mock_fn.assert_called_once_with(
            ["2411.15753"],
            ingest_only=False,
            compile_only=False,
            force=False,
        )

    @patch("scripts.ingest.ingest_and_compile")
    def test_cli_multiple_ids(self, mock_fn):
        """CLI passes multiple arXiv IDs."""
        mock_fn.return_value = {"ingested": 2, "compiled": 2, "failed": []}
        from scripts.ingest import main

        with patch("sys.argv", ["ingest", "2411.15753", "2503.08548"]):
            main()

        args, kwargs = mock_fn.call_args
        assert args[0] == ["2411.15753", "2503.08548"]

    @patch("scripts.ingest.ingest_and_compile")
    def test_cli_ingest_only(self, mock_fn):
        """CLI --ingest-only flag."""
        mock_fn.return_value = {"ingested": 1, "compiled": 0, "failed": []}
        from scripts.ingest import main

        with patch("sys.argv", ["ingest", "--ingest-only", "2411.15753"]):
            main()

        _, kwargs = mock_fn.call_args
        assert kwargs["ingest_only"] is True
        assert kwargs["compile_only"] is False

    @patch("scripts.ingest.ingest_and_compile")
    def test_cli_compile_only(self, mock_fn):
        """CLI --compile-only flag."""
        mock_fn.return_value = {"ingested": 0, "compiled": 1, "failed": []}
        from scripts.ingest import main

        with patch("sys.argv", ["ingest", "--compile-only", "2411.15753"]):
            main()

        _, kwargs = mock_fn.call_args
        assert kwargs["compile_only"] is True

    def test_cli_mutual_exclusion(self):
        """--ingest-only and --compile-only are mutually exclusive."""
        from scripts.ingest import main

        with patch("sys.argv", ["ingest", "--ingest-only", "--compile-only", "2411.15753"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    @patch("scripts.ingest.ingest_and_compile")
    def test_cli_force_flag(self, mock_fn):
        """CLI --force flag."""
        mock_fn.return_value = {"ingested": 1, "compiled": 1, "failed": []}
        from scripts.ingest import main

        with patch("sys.argv", ["ingest", "--force", "2411.15753"]):
            main()

        _, kwargs = mock_fn.call_args
        assert kwargs["force"] is True
