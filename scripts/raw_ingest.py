"""Raw data ingest layer: fetch and persist paper data to wiki/raw/."""

from __future__ import annotations

import io
import json
import logging
import re
import time
from datetime import date
from pathlib import Path

import requests
import yaml

from scripts.config import get_wiki_path
from scripts.fetch_paper import (
    fetch_arxiv_metadata,
    fetch_fulltext,
    fetch_s2_metadata,
)

logger = logging.getLogger(__name__)

RAW_PAPERS_DIR = "raw/papers"

# Image extraction limits (keep raw layer lightweight).
_MIN_IMAGE_DIM = 32       # skip tiny decorative glyphs / bullets
_MAX_IMAGES_PER_PAPER = 120

# Marker image filenames look like ``_page_{N}_Figure_{idx}.{ext}`` (also
# Picture, Table). Parse them so we can rewrite to our page{NNN}-img{MM}
# naming convention while preserving Marker's inline positions.
_MARKER_IMG_NAME_RE = re.compile(
    r"^_page_(\d+)_(Figure|Picture|Table|Equation|Caption|Formula)_(\d+)\.(\w+)$"
)

# Formula heuristic: a line is "math-heavy" if it contains Greek letters,
# math operators, or common LaTeX-style markers AND is relatively short.
_MATH_CHAR_RE = re.compile(
    r"[\u0370-\u03ff\u2200-\u22ff\u2a00-\u2aff\u27c0-\u27ef"  # Greek, math ops, misc math
    r"\u2190-\u21ff"                                          # arrows
    r"=≈≠≤≥±×÷∞∑∏∫√∂∇∈∉⊂⊆∩∪"
    r"]"
)
_MAX_FORMULA_LINES = 400


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_meta(
    arxiv_meta: dict,
    s2_meta: dict | None,
    assets: list[str],
) -> dict:
    """Merge arXiv and S2 metadata into the raw meta.yaml schema."""
    repo_url = None
    has_code = arxiv_meta.get("has_code", False)

    if s2_meta:
        has_code = has_code or s2_meta.get("has_code", False)

    today = date.today().isoformat()

    return {
        "id": arxiv_meta["arxiv_id"],
        "type": "paper",
        "title": arxiv_meta["title"],
        "authors": arxiv_meta["authors"],
        "date": arxiv_meta.get("date", ""),
        "venue": arxiv_meta.get("venue", "arXiv"),
        "url": arxiv_meta["url"],
        "pdf_url": arxiv_meta.get("pdf_url", ""),
        "repo_url": repo_url,
        "has_code": has_code,
        "fetched_at": today,
        "updated_at": today,
        "version": 1,
        "venue_status": "preprint",
        "assets": assets,
        "compile_status": {
            "compiled_at": None,
            "wiki_page": None,
            "stale": True,
        },
    }


def _write_meta_yaml(paper_dir: Path, meta: dict) -> Path:
    """Write meta.yaml to the given directory."""
    path = paper_dir / "meta.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(meta, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return path


def _fetch_pdf_bytes(arxiv_id: str, timeout: int = 60) -> bytes | None:
    """Download arXiv PDF bytes. Returns None on any failure."""
    url = f"https://arxiv.org/pdf/{arxiv_id}"
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.content
    except Exception:
        logger.debug("PDF download failed for %s", arxiv_id)
        return None


def extract_images(pdf_bytes: bytes, out_dir: Path) -> list[dict]:
    """Extract embedded images from a PDF into ``out_dir``.

    Saves each image as ``page{NNN}-img{MM}.{ext}`` and returns a manifest:

        [{"page": int, "index": int, "path": str, "width": int, "height": int,
          "ext": str, "bytes": int}, ...]

    ``path`` is relative to the paper's raw directory (i.e. starts with
    ``images/``) so it can be embedded in manifests without leaking
    absolute filesystem paths.

    Tiny images (< ``_MIN_IMAGE_DIM`` on either side) are skipped — these are
    usually bullets, dividers, or glyph fragments. Extraction is capped at
    ``_MAX_IMAGES_PER_PAPER`` to keep the raw layer bounded.
    """
    try:
        import pymupdf
    except ImportError:
        logger.debug("pymupdf not installed, skipping image extraction")
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []

    try:
        doc = pymupdf.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
    except Exception:
        logger.warning("PDF parsing failed during image extraction")
        return []

    try:
        saved = 0
        seen_xrefs: set[int] = set()
        for page_num, page in enumerate(doc, start=1):
            for img_index, img in enumerate(page.get_images(full=True)):
                if saved >= _MAX_IMAGES_PER_PAPER:
                    logger.info("Image cap reached (%d), stopping", saved)
                    break
                xref = img[0]
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)
                try:
                    base = doc.extract_image(xref)
                except Exception:
                    continue
                width = int(base.get("width") or 0)
                height = int(base.get("height") or 0)
                if width < _MIN_IMAGE_DIM or height < _MIN_IMAGE_DIM:
                    continue
                ext = base.get("ext") or "png"
                image_bytes: bytes = base.get("image") or b""
                if not image_bytes:
                    continue
                fname = f"page{page_num:03d}-img{img_index:02d}.{ext}"
                fpath = out_dir / fname
                fpath.write_bytes(image_bytes)
                manifest.append(
                    {
                        "page": page_num,
                        "index": img_index,
                        "path": f"images/{fname}",
                        "width": width,
                        "height": height,
                        "ext": ext,
                        "bytes": len(image_bytes),
                    }
                )
                saved += 1
            if saved >= _MAX_IMAGES_PER_PAPER:
                break
    finally:
        doc.close()

    return manifest


def _line_is_math_heavy(line: str) -> bool:
    """Heuristic: True if ``line`` looks like a formula or equation fragment."""
    stripped = line.strip()
    if len(stripped) < 3 or len(stripped) > 200:
        return False
    # Needs at least one math-signal character.
    if not _MATH_CHAR_RE.search(stripped):
        return False
    # Avoid full prose: lots of alpha chars but no math operators is not a formula.
    alpha = sum(ch.isalpha() and ch.isascii() for ch in stripped)
    math_hits = len(_MATH_CHAR_RE.findall(stripped))
    # Require math density — otherwise a sentence mentioning "α" slips in.
    if alpha > 0 and (math_hits / max(1, alpha)) < 0.08:
        return False
    return True


def extract_formulas(pdf_bytes: bytes) -> str | None:
    """Extract math-heavy text lines from a PDF as a first-pass formula dump.

    Returns a Markdown string with one line per detected formula grouped by
    page, or ``None`` if extraction is low-signal (fewer than 3 lines found)
    or PyMuPDF is unavailable.
    """
    try:
        import pymupdf
    except ImportError:
        return None

    try:
        doc = pymupdf.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
    except Exception:
        return None

    sections: list[str] = []
    total_lines = 0
    try:
        for page_num, page in enumerate(doc, start=1):
            if total_lines >= _MAX_FORMULA_LINES:
                break
            try:
                text = page.get_text("text") or ""
            except Exception:
                continue
            hits = [ln.strip() for ln in text.splitlines() if _line_is_math_heavy(ln)]
            if not hits:
                continue
            # De-duplicate within a page while preserving order.
            seen: set[str] = set()
            unique_hits = []
            for ln in hits:
                if ln in seen:
                    continue
                seen.add(ln)
                unique_hits.append(ln)
            sections.append(f"## Page {page_num}\n\n" + "\n".join(f"- `{ln}`" for ln in unique_hits))
            total_lines += len(unique_hits)
    finally:
        doc.close()

    if total_lines < 3:
        return None
    header = "# Extracted formula candidates\n\nHeuristic line-level extraction (not LaTeX-perfect).\n\n"
    return header + "\n\n".join(sections) + "\n"


# ---------------------------------------------------------------------------
# Marker-based fulltext extraction (inline LaTeX)
# ---------------------------------------------------------------------------

# Lazy-loaded singleton — Marker's model dict is expensive to build (~5-15s),
# so we cache it across paper iterations. A single import/process can reuse
# the same converter.
_MARKER_CONVERTER = None


def _get_marker_converter():
    """Lazily build and cache a Marker PdfConverter."""
    global _MARKER_CONVERTER
    if _MARKER_CONVERTER is not None:
        return _MARKER_CONVERTER
    try:
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
    except ImportError:
        logger.warning("marker-pdf not installed; cannot extract inline LaTeX")
        return None
    logger.info("Loading Marker models (one-time)...")
    models = create_model_dict()
    _MARKER_CONVERTER = PdfConverter(artifact_dict=models)
    return _MARKER_CONVERTER


def extract_fulltext_with_latex(
    pdf_bytes: bytes,
    *,
    converter=None,
) -> str | None:
    """Convert a PDF to markdown with inline LaTeX formulas via Marker.

    Returns a markdown string (with `$...$` and `$$...$$` LaTeX formulas
    inlined alongside the prose) or ``None`` if marker-pdf is unavailable or
    the conversion fails.

    ``converter`` — optional pre-initialised Marker ``PdfConverter``. When
    processing many PDFs in a single process, pass the same converter in to
    avoid reloading models between papers.
    """
    result = extract_fulltext_and_images_with_marker(pdf_bytes, converter=converter)
    if result is None:
        return None
    md_text, _images = result
    return md_text


def extract_fulltext_and_images_with_marker(
    pdf_bytes: bytes,
    *,
    converter=None,
) -> tuple[str, dict] | None:
    """Run Marker end-to-end and return ``(markdown, images)``.

    ``images`` is Marker's raw ``{filename: PIL.Image}`` dict where each
    filename matches a ``![](filename)`` reference already placed at the
    correct inline position in ``markdown``. Returns ``None`` on any
    failure (marker missing, empty input, converter exception).

    ``converter`` — optional pre-initialised Marker ``PdfConverter`` to
    reuse across papers; avoids paying model-load cost per paper.
    """
    if not pdf_bytes:
        return None

    conv = converter if converter is not None else _get_marker_converter()
    if conv is None:
        return None

    import tempfile
    from marker.output import text_from_rendered

    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name
        rendered = conv(tmp_path)
        md_text, _, images = text_from_rendered(rendered)
        return md_text, (images or {})
    except Exception:
        logger.exception("Marker fulltext extraction failed")
        return None
    finally:
        if tmp_path is not None:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass


def _parse_marker_image_name(name: str) -> tuple[int, int, str] | None:
    """Parse ``_page_{N}_{Kind}_{idx}.{ext}`` → ``(page, index, ext)``.

    Marker pages are 0-indexed in the filename, so we return ``N + 1`` to
    match PyMuPDF's 1-indexed page numbering. Returns ``None`` if the name
    doesn't match the expected shape.
    """
    m = _MARKER_IMG_NAME_RE.match(name)
    if not m:
        return None
    page_zero, _kind, idx, ext = m.groups()
    try:
        return int(page_zero) + 1, int(idx), ext.lower()
    except ValueError:
        return None


def save_marker_images(
    images: dict,
    out_dir: Path,
    *,
    markdown: str,
) -> tuple[list[dict], str]:
    """Save Marker's image dict to ``out_dir`` under ``page{NNN}-img{MM}.{ext}``.

    Returns ``(manifest, rewritten_markdown)``:

    * ``manifest`` — list of dicts with ``page``, ``index``, ``path``,
      ``width``, ``height``, ``ext``, ``bytes``, sorted by (page, index).
    * ``rewritten_markdown`` — ``markdown`` with every Marker image
      reference (``![](_page_N_Kind_i.ext)``) rewritten to the new
      ``images/page{NNN}-img{MM}.{ext}`` path.

    Images smaller than ``_MIN_IMAGE_DIM`` on either side are dropped and
    their markdown references are stripped. Extraction is capped at
    ``_MAX_IMAGES_PER_PAPER`` to keep the raw layer bounded.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    rename_map: dict[str, str] = {}  # old name → new relative path (or "" to drop)
    saved = 0

    # Stable order: sort by parsed (page, index) so the NN suffix is deterministic.
    sort_key = lambda name: _parse_marker_image_name(name) or (10**9, 10**9, "")
    for name in sorted(images.keys(), key=sort_key):
        if saved >= _MAX_IMAGES_PER_PAPER:
            rename_map[name] = ""  # drop overflow
            continue
        parsed = _parse_marker_image_name(name)
        if parsed is None:
            rename_map[name] = ""
            continue
        page, index, ext = parsed
        pil = images[name]
        width = getattr(pil, "width", 0) or 0
        height = getattr(pil, "height", 0) or 0
        if width < _MIN_IMAGE_DIM or height < _MIN_IMAGE_DIM:
            rename_map[name] = ""
            continue
        buf = io.BytesIO()
        fmt = "JPEG" if ext in ("jpg", "jpeg") else ext.upper()
        try:
            if pil.mode not in ("RGB", "L") and fmt == "JPEG":
                pil = pil.convert("RGB")
            pil.save(buf, format=fmt)
        except Exception:
            logger.warning("Failed to save marker image %s", name)
            rename_map[name] = ""
            continue
        data = buf.getvalue()
        fname = f"page{page:03d}-img{index:02d}.{ext}"
        (out_dir / fname).write_bytes(data)
        rel = f"images/{fname}"
        manifest.append(
            {
                "page": page,
                "index": index,
                "path": rel,
                "width": int(width),
                "height": int(height),
                "ext": ext,
                "bytes": len(data),
            }
        )
        rename_map[name] = rel
        saved += 1

    rewritten = _rewrite_marker_refs(markdown, rename_map)
    return manifest, rewritten


def _rewrite_marker_refs(markdown: str, rename_map: dict[str, str]) -> str:
    """Rewrite ``![alt](old_name)`` → ``![alt](new_path)``.

    Entries mapped to empty string are dropped (the whole image ref removed).
    """
    def _sub(match: re.Match[str]) -> str:
        alt = match.group(1)
        target = match.group(2).strip()
        if target in rename_map:
            new = rename_map[target]
            if not new:
                return ""  # drop orphaned reference entirely
            return f"![{alt}]({new})"
        return match.group(0)

    # ![alt](target)  — target has no whitespace, no parens
    pattern = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
    return pattern.sub(_sub, markdown)


def _fetch_repo_readme(repo_url: str, timeout: int = 30) -> str | None:
    """Fetch README from a GitHub repository URL.

    Tries main branch first, then falls back to master.
    """
    if not repo_url or "github.com" not in repo_url:
        return None

    # Extract owner/repo from URL
    parts = repo_url.rstrip("/").split("github.com/")
    if len(parts) < 2:
        return None
    owner_repo = parts[1].split("/")
    if len(owner_repo) < 2:
        return None
    owner, repo = owner_repo[0], owner_repo[1]

    for branch in ("main", "master"):
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/README.md"
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200 and len(resp.text) > 100:
                return resp.text
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ingest_paper(
    arxiv_id: str,
    wiki_dir: Path | None = None,
    *,
    force: bool = False,
) -> Path:
    """Ingest a paper into the raw layer.

    Fetches metadata, fulltext, and optionally repo README.
    Creates wiki/raw/papers/{arxiv_id}/ with meta.yaml + content files.
    Idempotent: skips if meta.yaml already exists unless force=True.

    Returns the path to the paper's raw directory.
    """
    resolved = wiki_dir if wiki_dir is not None else get_wiki_path()
    paper_dir = resolved / RAW_PAPERS_DIR / arxiv_id
    meta_path = paper_dir / "meta.yaml"

    if meta_path.exists() and not force:
        logger.info("Raw data already exists for %s, skipping", arxiv_id)
        return paper_dir

    paper_dir.mkdir(parents=True, exist_ok=True)

    # Fetch metadata
    arxiv_meta = fetch_arxiv_metadata(arxiv_id)
    if arxiv_meta is None:
        raise ValueError(f"Failed to fetch arXiv metadata for {arxiv_id}")

    s2_meta = None
    try:
        s2_meta = fetch_s2_metadata(arxiv_id=arxiv_id)
    except Exception:
        logger.warning("S2 metadata fetch failed for %s, continuing", arxiv_id)

    # Fulltext + asset extraction.
    #
    # Prefer Marker (PDF → markdown with inline LaTeX) when available, since
    # that gives us formulas and prose in one coherent file — which is what
    # the wiki compiler wants to cite directly. Fall back to the old HTML
    # fetch path when Marker isn't installed or crashes.
    assets: list[str] = []
    fulltext_path = paper_dir / "fulltext.md"
    images_manifest_path = paper_dir / "images.json"
    images_dir = paper_dir / "images"
    formulas_path = paper_dir / "formulas.md"

    needs_fulltext = force or not fulltext_path.exists()
    needs_images = force or not images_manifest_path.exists()
    needs_formulas = force or not formulas_path.exists()

    pdf_bytes: bytes | None = None
    if needs_fulltext or needs_images or needs_formulas:
        pdf_bytes = _fetch_pdf_bytes(arxiv_id)

    fulltext_written = False
    if needs_fulltext and pdf_bytes:
        try:
            latex_md = extract_fulltext_with_latex(pdf_bytes)
        except Exception:
            logger.exception("Marker fulltext extraction failed for %s", arxiv_id)
            latex_md = None
        if latex_md:
            fulltext_path.write_text(latex_md, encoding="utf-8")
            logger.info(
                "Saved Marker fulltext for %s (%d chars)", arxiv_id, len(latex_md)
            )
            fulltext_written = True

    if needs_fulltext and not fulltext_written:
        # Marker unavailable or failed — fall back to the legacy HTML fetch.
        fulltext = fetch_fulltext(arxiv_id)
        if fulltext:
            fulltext_path.write_text(fulltext, encoding="utf-8")
            logger.info(
                "Saved legacy fulltext for %s (%d chars)", arxiv_id, len(fulltext)
            )
            fulltext_written = True

    if fulltext_path.exists():
        assets.append("fulltext.md")

    if pdf_bytes:
        if needs_images:
            try:
                manifest = extract_images(pdf_bytes, images_dir)
            except Exception:
                logger.exception("Image extraction failed for %s", arxiv_id)
                manifest = []
            with open(images_manifest_path, "w", encoding="utf-8") as f:
                json.dump({"images": manifest}, f, ensure_ascii=False, indent=2)
            if manifest:
                logger.info("Extracted %d images for %s", len(manifest), arxiv_id)
        if needs_formulas:
            try:
                formulas = extract_formulas(pdf_bytes)
            except Exception:
                logger.exception("Formula extraction failed for %s", arxiv_id)
                formulas = None
            if formulas:
                formulas_path.write_text(formulas, encoding="utf-8")
                logger.info("Saved formula candidates for %s", arxiv_id)
    elif needs_images or needs_formulas:
        logger.info(
            "No PDF bytes available for %s; skipping image/formula extraction",
            arxiv_id,
        )

    # Re-read manifest to report in assets (empty manifest still counts as "ran").
    if images_manifest_path.exists():
        try:
            with open(images_manifest_path, encoding="utf-8") as f:
                stored = json.load(f)
            if stored.get("images"):
                assets.append("images.json")
        except Exception:
            logger.warning("Failed to re-read images manifest for %s", arxiv_id)
    if formulas_path.exists():
        assets.append("formulas.md")

    # Fetch repo README if code exists
    repo_url = None
    if s2_meta and s2_meta.get("has_code"):
        # S2 doesn't provide repo_url directly; we'll skip for now
        pass
    if arxiv_meta.get("project_url"):
        repo_url = arxiv_meta["project_url"]

    if repo_url:
        readme = _fetch_repo_readme(repo_url)
        if readme:
            readme_path = paper_dir / "repo-readme.md"
            readme_path.write_text(readme, encoding="utf-8")
            assets.append("repo-readme.md")
            logger.info("Saved repo README for %s", arxiv_id)

    # Build and write meta.yaml
    meta = _build_meta(arxiv_meta, s2_meta, assets)
    if repo_url:
        meta["repo_url"] = repo_url
    _write_meta_yaml(paper_dir, meta)
    logger.info("Ingested raw data for %s: %s", arxiv_id, arxiv_meta["title"])

    return paper_dir


def reextract_fulltext(
    arxiv_id: str,
    wiki_dir: Path | None = None,
    *,
    converter=None,
) -> dict:
    """Re-extract ``fulltext.md`` for an already-ingested paper using Marker.

    Does not touch arXiv metadata or images/ — only fetches the PDF and
    overwrites ``fulltext.md`` with Marker's inline-LaTeX markdown. Use this
    to backfill high-quality fulltext onto papers that were originally
    ingested with the legacy HTML fetch.

    Returns a dict with ``status`` ("ok" | "skipped" | "failed"), ``chars``,
    and ``formulas`` (count of `$...$` / `$$...$$` delimiters in the output).
    """
    resolved = wiki_dir if wiki_dir is not None else get_wiki_path()
    paper_dir = resolved / RAW_PAPERS_DIR / arxiv_id
    meta_path = paper_dir / "meta.yaml"
    if not meta_path.exists():
        return {"status": "skipped", "reason": "no meta.yaml", "chars": 0, "formulas": 0}

    pdf_bytes = _fetch_pdf_bytes(arxiv_id)
    if not pdf_bytes:
        return {"status": "failed", "reason": "pdf download failed", "chars": 0, "formulas": 0}

    md_text = extract_fulltext_with_latex(pdf_bytes, converter=converter)
    if not md_text:
        return {"status": "failed", "reason": "marker extraction failed", "chars": 0, "formulas": 0}

    fulltext_path = paper_dir / "fulltext.md"
    fulltext_path.write_text(md_text, encoding="utf-8")

    # Update meta.yaml assets list + updated_at, preserving everything else.
    try:
        with open(meta_path, encoding="utf-8") as f:
            meta = yaml.safe_load(f) or {}
        assets = list(meta.get("assets") or [])
        if "fulltext.md" not in assets:
            assets.append("fulltext.md")
        meta["assets"] = assets
        meta["updated_at"] = date.today().isoformat()
        with open(meta_path, "w", encoding="utf-8") as f:
            yaml.dump(meta, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    except Exception:
        logger.exception("Failed to update meta.yaml for %s", arxiv_id)

    # Count formula delimiters: each `$` or `$$` pair is one formula.
    # Block-level `$$...$$` counts as one; inline `$...$` counts as one.
    block_count = md_text.count("$$") // 2
    # Inline `$` pairs: remaining dollars after removing block delimiters.
    text_no_blocks = re.sub(r"\$\$[^$]*\$\$", "", md_text)
    inline_count = text_no_blocks.count("$") // 2
    formula_count = block_count + inline_count

    return {
        "status": "ok",
        "chars": len(md_text),
        "formulas": formula_count,
    }


def reextract_images(
    arxiv_id: str,
    wiki_dir: Path | None = None,
    *,
    converter=None,
) -> dict:
    """Re-run Marker to extract images and inject inline refs into ``fulltext.md``.

    Idempotent-ish: always overwrites ``fulltext.md``, ``images/`` and
    ``images.json`` for the paper. Call this to backfill images onto
    already-ingested papers (Task #39 batch) without re-fetching arXiv
    metadata.

    Returns a dict with ``status`` ("ok" | "skipped" | "failed"),
    ``images`` (count saved), ``chars``, ``refs`` (count of inline image
    refs in the rewritten markdown), and ``reason`` on failure.
    """
    resolved = wiki_dir if wiki_dir is not None else get_wiki_path()
    paper_dir = resolved / RAW_PAPERS_DIR / arxiv_id
    meta_path = paper_dir / "meta.yaml"
    if not meta_path.exists():
        return {"status": "skipped", "reason": "no meta.yaml", "images": 0, "chars": 0, "refs": 0}

    pdf_bytes = _fetch_pdf_bytes(arxiv_id)
    if not pdf_bytes:
        return {"status": "failed", "reason": "pdf download failed", "images": 0, "chars": 0, "refs": 0}

    result = extract_fulltext_and_images_with_marker(pdf_bytes, converter=converter)
    if result is None:
        return {"status": "failed", "reason": "marker extraction failed", "images": 0, "chars": 0, "refs": 0}
    md_text, raw_images = result

    # Persist images with our naming convention and rewrite markdown refs.
    # Wipe any legacy files first so we don't leave stale PyMuPDF extractions
    # in place alongside fresh Marker output.
    images_dir = paper_dir / "images"
    if images_dir.exists():
        for stale in images_dir.glob("*"):
            if stale.is_file():
                try:
                    stale.unlink()
                except OSError:
                    logger.warning("Failed to remove stale image %s", stale)
    manifest, rewritten_md = save_marker_images(raw_images, images_dir, markdown=md_text)

    fulltext_path = paper_dir / "fulltext.md"
    fulltext_path.write_text(rewritten_md, encoding="utf-8")

    manifest_path = paper_dir / "images.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({"images": manifest}, f, ensure_ascii=False, indent=2)

    # Update meta.yaml: add images/ + images.json assets and bump updated_at.
    try:
        with open(meta_path, encoding="utf-8") as f:
            meta = yaml.safe_load(f) or {}
        assets = list(meta.get("assets") or [])
        for a in ("fulltext.md", "images.json", "images/"):
            if a not in assets:
                assets.append(a)
        meta["assets"] = assets
        meta["updated_at"] = date.today().isoformat()
        with open(meta_path, "w", encoding="utf-8") as f:
            yaml.dump(meta, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    except Exception:
        logger.exception("Failed to update meta.yaml for %s", arxiv_id)

    ref_count = len(re.findall(r"!\[[^\]]*\]\(images/", rewritten_md))
    return {
        "status": "ok",
        "images": len(manifest),
        "chars": len(rewritten_md),
        "refs": ref_count,
    }


def ingest_batch(
    arxiv_ids: list[str],
    wiki_dir: Path | None = None,
    *,
    delay: float = 1.0,
    force: bool = False,
) -> dict:
    """Batch-ingest multiple papers into the raw layer.

    Returns {ingested: int, skipped: int, failed: list[str]}.
    """
    ingested = 0
    skipped = 0
    failed: list[str] = []

    for i, arxiv_id in enumerate(arxiv_ids):
        try:
            resolved = wiki_dir if wiki_dir is not None else get_wiki_path()
            meta_path = resolved / RAW_PAPERS_DIR / arxiv_id / "meta.yaml"

            if meta_path.exists() and not force:
                skipped += 1
                logger.info("[%d/%d] Skipped %s (exists)", i + 1, len(arxiv_ids), arxiv_id)
                continue

            ingest_paper(arxiv_id, wiki_dir, force=force)
            ingested += 1
            logger.info("[%d/%d] Ingested %s", i + 1, len(arxiv_ids), arxiv_id)

            if i < len(arxiv_ids) - 1:
                time.sleep(delay)

        except Exception:
            logger.exception("[%d/%d] Failed to ingest %s", i + 1, len(arxiv_ids), arxiv_id)
            failed.append(arxiv_id)

    return {"ingested": ingested, "skipped": skipped, "failed": failed}


def load_raw_meta(arxiv_id: str, wiki_dir: Path | None = None) -> dict | None:
    """Load meta.yaml for a given paper. Returns None if not found."""
    resolved = wiki_dir if wiki_dir is not None else get_wiki_path()
    meta_path = resolved / RAW_PAPERS_DIR / arxiv_id / "meta.yaml"
    if not meta_path.exists():
        return None
    with open(meta_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_raw_content(arxiv_id: str, wiki_dir: Path | None = None) -> dict:
    """Load all raw content for a paper.

    Returns {"meta": dict, "fulltext": str | None, "repo_readme": str | None}.
    Raises FileNotFoundError if the raw directory doesn't exist.
    """
    resolved = wiki_dir if wiki_dir is not None else get_wiki_path()
    paper_dir = resolved / RAW_PAPERS_DIR / arxiv_id

    if not paper_dir.exists():
        raise FileNotFoundError(f"Raw data not found for {arxiv_id}")

    meta = load_raw_meta(arxiv_id, wiki_dir)
    if meta is None:
        raise FileNotFoundError(f"meta.yaml not found for {arxiv_id}")

    fulltext_path = paper_dir / "fulltext.md"
    fulltext = fulltext_path.read_text(encoding="utf-8") if fulltext_path.exists() else None

    readme_path = paper_dir / "repo-readme.md"
    repo_readme = readme_path.read_text(encoding="utf-8") if readme_path.exists() else None

    return {
        "meta": meta,
        "fulltext": fulltext,
        "repo_readme": repo_readme,
    }
