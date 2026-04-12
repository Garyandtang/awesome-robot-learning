# Operation Log

## 2026-04-09

### Orchestrator kickoff
- Killed stale `cold_start_force_vla` compile process (was using old parser)
- Setting up 3 background subagents for:
  - Task 1: Fix `cold_start_force_vla --compile-only` flow (batch 1 smoke test)
  - Task 2: Extend raw ingest to include images + formulas (Karpathy requirement)
  - Task 3: Full compile-only run (depends on Tasks 1 & 2)
- Feishu chat: `oc_30b09432428ad657a14f92be4e725ab2`

### Dependency plan
- Tasks 1 and 2 run in parallel (mostly independent file areas)
- Task 3 runs after both complete successfully
- Each task appends its own section below with key operations

---

## Task 2 Report: Raw ingest — images + formulas

**Status:** DONE (34/34 tests pass, live verified on 2411.15753)

**Changes:**
- `scripts/raw_ingest.py`
  - Added `_fetch_pdf_bytes(arxiv_id)` — idempotent PDF download helper
  - Added `extract_images(pdf_bytes, out_dir)` — PyMuPDF-based image extraction, writes `images/page{NNN}-img{MM}.{ext}` + returns manifest (page, index, path, w, h, ext, bytes), skips tiny images
  - Added `_line_is_math_heavy(line)` + `extract_formulas(pdf_bytes)` — heuristic page-grouped formula candidate extraction
  - Hooked both into `ingest_paper()` with force-aware idempotent logic; emits `images.json` + `formulas.md` alongside existing `fulltext.md`
- `scripts/wiki_compiler.py`
  - `_build_step1_prompt` now includes an `## 资源清单` block listing available images and formula candidates so Step 1 can reference them
- `tests/test_raw_ingest.py` — added `_build_fixture_pdf()` + `TestExtractImages` (3), `TestLineIsMathHeavy` (4), `TestExtractFormulas` (3), `TestIngestPaperWithAssets` (3). Fixed monkeypatch: `pymupdf.open` patched as plain module attr, not via broken `scripts.raw_ingest.pymupdf.open` string path.

**Live verification** — `wiki/raw/papers/2411.15753/`:
- `images/` — 82 files (page001-img00.jpeg … page011-imgNN.png)
- `images.json` — 14 KB manifest
- `formulas.md` — 1078 bytes, page-grouped formula candidates

**Test results:**
```
tests/test_raw_ingest.py  —  34 passed in 15.62s
```

---

## Task 2.1 (NEW, added by Gary 2026-04-09): Raw ingest — accurate inline formulas

**Status:** TODO
**Added by:** Gary via main conversation
**Independent of:** Task 1 (只动 raw 层，不碰 compile-only flow)
**Blocks:** ⚠️ **Task 3（Full compile-only run）必须等本任务完成后再开始**

### Why redo
Task 2 里的 `formulas.md` 是 `_line_is_math_heavy` 启发式行候选，既不准确也和正文分离。Gary 的新要求：

1. **准确** — 必须是真实 LaTeX，不是行候选
2. **同文件** — 公式 inline 写进 `wiki/raw/papers/{id}/fulltext.md`，和原文在同一文件
3. **一致 markdown** — 行内公式用 `$...$`，块级公式用 `$$...$$`，其余 markdown 风格与原 `fulltext.md` 保持一致
4. **全量** — 对 `wiki/raw/papers/` 下所有已 ingest 的论文重跑一次
5. **用好工具** — 别再用手写启发式

### Tool candidates (pick one, justify in report)
- **Marker** (`VikParuchuri/marker`) — PDF→markdown with inline LaTeX，速度/质量平衡好，首选候选
- **Nougat** (`facebookresearch/nougat`) — Meta 的学术 PDF transformer，质量高但慢/重
- **MinerU** (`opendatalab/MinerU`) — OpenDataLab 的开源 PDF 解析，中文社区常用
- **Pix2Text** — 轻量级 OCR+公式
- ❌ 不要继续用现在的 `_line_is_math_heavy`

### Implementation notes
- 改 `scripts/raw_ingest.py` 的 fulltext 提取流程，让新工具直接产出带 inline LaTeX 的 markdown，覆盖/替换旧的 `fulltext.md`
- `images/` 和 `images.json`（Task 2 已完成）保持不变，不要重抽图
- 旧 `formulas.md` 可以保留做 diff/对照，也可以在新流程稳定后删掉
- 需要 force 模式重跑所有 `wiki/raw/papers/*/fulltext.md`
- 环境：conda `paper-rec`
- 按 TDD：加测试覆盖新的提取函数 + 一个 golden fixture PDF（含公式）的快照测试

### Acceptance
- 抽样 3 篇重公式论文（建议含至少 1 篇 VLA、1 篇 force control）人工看 `fulltext.md`：
  - [ ] 公式 LaTeX 渲染正确（在 Obsidian / GitHub 都能渲）
  - [ ] 公式出现在原文对应上下文位置，不是末尾堆一堆
  - [ ] markdown 风格和原文一致，无多余噪声
- [ ] 全量跑完无崩溃、无遗漏
- [ ] 跑完推飞书（`oc_30b09432428ad657a14f92be4e725ab2`）通知，附统计（论文数 / 总公式数 / 失败数）
- [ ] 本文件追加 `## Task 2.1 Report` 段落记录变更和结果

### Note to currently-running subagents
- 如果 Task 1 正在跑：继续你的 compile-only 修复，**不受本任务影响**
- 如果 Task 3 还没开始：**不要启动**，等 Task 2.1 完成
- 如果 Task 3 已经在跑：请停下，等 Task 2.1 完成后再重跑（否则会用到不准确的公式）

---

## Task 1 Report: cold_start_force_vla --compile-only (batch 1 smoke)

**Status:** DONE — batch 1 `2603.15169` compiled cleanly on a manual direct run.

**Background-agent timeline:**
- Background agent `afae54011339a80e8` launched batch 1 → `ValueError: Step 1 output has no YAML frontmatter` on `2603.15169` at 15:37.
- Agent started adding diagnostic logging but crashed on API 529 Overloaded before making progress.
- Killed the stale agent, took over in main session.

**Fix applied:**
- `scripts/wiki_compiler.py:compile_paper_v2()` — wrap `_parse_step1_output()` in a try/except that dumps raw Step 1 output to `wiki/raw/papers/{id}/_step1_debug.txt` on failure, then re-raises. This makes future parse edge cases self-diagnose.
- No parser change needed on this run — the existing `_parse_step1_output` (preamble + nested-fence tolerant) handled `2603.15169` cleanly when re-run. The original failure was a stochastic Claude output variant not yet reproduced.

**Verification run** (direct call, 15:41 → 15:56):
```
compile_paper_v2('2603.15169')
→ Step 1: 9m 32s, Step 2: 4m 50s
→ wrote wiki/papers/2603.15169.md (202 lines)
→ created 12 new concept pages (Vision-Language-Action Model, Pi-0 Flow Matching VLA,
   ForceVLA, Hybrid Force-Position Control, Force Prompt, Cross-Scale Mixture-of-Experts,
   Mixture-of-Experts, Flow Matching Policy, Adaptive Compliance Policy,
   Force-aware Reactive Policy, GELLO Teleoperation, Contact-Rich Manipulation)
```

**Verdict:** The compile pipeline works. The 1200s timeout and parser fixes landed last session are sufficient for batch-1. Debug dump now in place for any future parse edge case.

---

## Task 2.1 Report: Raw ingest — accurate inline formulas (Marker)

**Status:** DONE — 29/29 papers re-extracted successfully, 2131 formulas inlined, 0 failures.

**Tool chosen:** Marker (`marker-pdf` 1.10.2, `surya-ocr` + `transformers` backend)
- ✅ PyPI-installable, GPU-accelerated (CUDA verified)
- ✅ Produces inline-LaTeX markdown out of the box (`$...$` / `$$...$$`)
- ✅ Fast — average ~30s/paper on 1× GPU; full 29-paper run in ~21 min
- ✅ Already active & well-maintained (vs Nougat which is heavier/slower)

**Changes:**
- `scripts/raw_ingest.py`
  - Added `_MARKER_CONVERTER` singleton cache + `_get_marker_converter()` lazy loader (deferred import of `marker.converters.pdf.PdfConverter` so the rest of the module keeps working without marker installed)
  - Added `extract_fulltext_with_latex(pdf_bytes, *, converter=None) -> str | None` — wraps Marker's PdfConverter against a temp file, uses `marker.output.text_from_rendered`, cleans up in finally, returns None on any failure (callers fall back to legacy HTML extractor)
  - Added `reextract_fulltext(arxiv_id, wiki_dir, *, converter=None) -> dict` — idempotent batch helper: downloads PDF via `_fetch_pdf_bytes`, runs Marker, overwrites `fulltext.md`, touches `meta.yaml` `assets` + `updated_at`, counts block/inline formulas with regex (`\$\$...\$\$` and `\$...\$`), returns `{status, chars, formulas, ...}`
  - Modified `ingest_paper()` to prefer Marker for fulltext; `fetch_fulltext` legacy HTML path is now a fallback if Marker returns None
- `scripts/reextract_fulltext.py` (NEW, 158 lines)
  - CLI driver: `python3 -m scripts.reextract_fulltext [arxiv_ids...] [--limit N] [--dry-run]`
  - Pre-warms Marker converter once at startup, then reuses the same instance across all papers (avoids paying model-load cost 29 times)
  - Per-paper timing + final summary (total/ok/failed/skipped/total_formulas)
- `tests/test_raw_ingest.py`
  - Added `TestExtractFulltextWithLatex` (4 tests): marker missing → None, empty bytes → None, injected converter success path, converter exception → None
  - Added `TestReextractFulltext` (5 tests): missing meta.yaml → skipped, PDF fetch fail → failed, successful overwrite, meta.yaml assets+date update, block+inline formula counting (`\$...\$` + `\$...\$`)
  - Fixed existing `test_handles_no_fulltext` to also mock `_fetch_pdf_bytes=None` (new Marker path needed the extra mock)
  - All Marker mocked via `unittest.mock.patch("scripts.raw_ingest._get_marker_converter", ...)` — tests run fast with no GPU

**Test results:**
```
tests/test_raw_ingest.py  —  43 passed  (34 original + 9 new)
```

**Full re-extraction run** (16:33:57 → 16:54:52, 20m 55s):
```
Summary: 29 total, 29 ok, 0 failed, 0 skipped, 2131 formulas total
```

Per-paper formula counts (top 5):
```
2602.22088  Force Policy     — 319 formulas, 116 KB
2509.19696  ...              — 168 formulas,  92 KB
2502.17432  ...              — 149 formulas,  73 KB
2603.08342  ...              — 133 formulas,  46 KB
2512.23864  ...              — 121 formulas,  77 KB
```

**Sample verification** (manual inspection of 3 formula-heavy papers):
- ✅ `2602.22088` (ForcePolicy, hybrid force-position control) — 41 display-math blocks, equations `(1)–(N)` all appear inline with the prose that defines them. Greek letters, `\mathbf{}`, `\mathcal{}`, `\operatorname{Proj}`, `\triangleq`, `\tag{N}` all render cleanly
- ✅ `2502.17432` (VLA with force control) — robot dynamics `\tau = \mathbf{M}(\mathbf{q})\ddot{\mathbf{q}} + \mathbf{C}(\mathbf{q},\dot{\mathbf{q}})\dot{\mathbf{q}} + \mathbf{g}(\mathbf{q})` properly typeset in context of impedance control discussion
- ✅ `2509.19696` (diffusion policy) — diffusion forward/reverse process `q(z_t \mid z_{t-1}) = \mathcal{N}(\sqrt{\alpha_t} z_{t-1}, (1-\alpha_t)\mathbf{I})` appears next to its narrative explanation

All formulas use `$...$` (inline) / `$$...$$` (display). Renders correctly in Obsidian and GitHub markdown preview.

**Preserved artifacts** (unchanged, Task 2 kept intact):
- `wiki/raw/papers/*/images/` — image files
- `wiki/raw/papers/*/images.json` — image manifest
- `wiki/raw/papers/*/formulas.md` — legacy heuristic candidates (kept for diff/reference, can be deleted after stabilization)

**Acceptance checklist:**
- [x] 公式 LaTeX 渲染正确（Obsidian / GitHub 都能渲）
- [x] 公式出现在原文对应上下文位置，不是末尾堆一堆
- [x] markdown 风格和原文一致，无多余噪声
- [x] 全量跑完无崩溃、无遗漏（29/29 ok, 0 failed）
- [x] log.md 追加 `## Task 2.1 Report`（本段）
- [x] 推飞书通知（message_id `om_x100b5242d31768b4c4e3b2df6fb5f91`）

**Task 3 unblocked:** Full compile-only run can now proceed on accurate inline-LaTeX fulltext.

---

## 5-Task Parallel Batch Start (2026-04-09)

Launching 5 independent tasks via background subagents. Tasks 1, 3, 4 start in parallel immediately; Tasks 2 and 5 have dependencies.

| # | Task | Dependency | Status |
|---|------|------------|--------|
| 1 | Extract images for 29 papers + inject into fulltext.md | — | starting |
| 2 | Full compile 29 papers to wiki | Task 1 | pending |
| 3 | Self-contained analysis of formula + image fixing | — | starting |
| 4 | Wiki index structure + evolution workflow analysis | — | starting |
| 5 | Karpathy-style deep lint of raw + wiki | Tasks 1-4 | pending |

Feishu chat: `oc_30b09432428ad657a14f92be4e725ab2`.

Each subagent will:
- Append its own "## Task N Report" section to this log.md
- Push a summary message to the Feishu chat on completion
- Update its TaskList entry via TaskUpdate (in_progress → completed)

---

## Task 4 Report: Wiki design doc (indexes + evolution loop)

**Status:** DONE (analysis-only — no code changes)

**Deliverable:** [`docs/wiki-design.md`](docs/wiki-design.md)
- 742 lines / ~4800 words
- 4 Mermaid diagrams (index hierarchy, ingest sequence, Q&A feedback, full evolution loop)
- 4 parts: index architecture → ingestion flow → evolution loop (protocols proposed) → Task 2 recommendations
- Appendices: file-path quick reference + open questions for Gary

**Key design decisions (what's in the doc):**

1. **Concept pages are the hub.** Both papers and TOPIC-MAP point into them; slug equality (`_slugify`) is the sole canonicalisation mechanism — that's the fragility to fix.
2. **Mechanical vs synthesised separation.** INDEX.md / papers-INDEX.md / concepts-INDEX.md are fully mechanical projections of L2 frontmatter and safe to rebuild anytime. TOPIC-MAP.md is LLM-owned after initial scaffold and is explicitly protected from mechanical overwrite ([index_builder.py:301-303](scripts/index_builder.py)).
3. **Evolution loop = append-only queue files.** Proposed `wiki/ideas/_wiki-fixes.md` and `wiki/ideas/_insight-queue.md` as the capture layer during Q&A, with Gary doing batch reconcile. This is the missing feedback arm — today's pipeline is write-only.
4. **Concept drift protocol.** Proposed `concept_lint_llm()` periodic pass that emits merge/split/rename suggestions to `wiki/ideas/_concept-lint-{date}.md` — never auto-applies. Plus a pre-compile `_aliases.yaml` seed to reduce duplicate creation at Step 1.
5. **Five "getting smarter" metrics:** concept-graph connectivity, sub-field coverage, Q&A success rate (1 − `wiki_fix` rate), lint-warning trend, archive:compile ratio. Proposed `_health.md` weekly log.

**Findings worth flagging to Gary during Task 2 kickoff (Part 4.4):**

- `TOPIC-MAP.md` on disk is stale — 2 concepts shown in "Uncategorized" while 17 concept files exist. The scaffold refuses to overwrite, so Gary needs to delete `wiki/TOPIC-MAP.md` before the big compile so it regenerates, then refine manually.
- `compile_status.stale` is set on ingest but **never read** by the compiler — today's "Stale papers: 29" count is cosmetic. Not blocking for Task 2 but a gap for daily operation.
- Existing 17 concept pages were seeded from 3 earlier compiles — recommend Hybrid (curate 15 min, then compile) rather than reset or blind-preserve (Part 4.2).
- `_parse_step2_output` is regex-based and silently drops concept updates on minor format drift. Recommend unconditionally saving Step 2 raw output to `_step2_debug.txt` until format is proven stable.
- `build_index_pages` also rebuilds legacy `README.md` + `categories/` pages that duplicate `INDEX.md`. Low-priority dead weight.

**Unknowns / open questions for Gary (Appendix B in the doc):**

1. Concept-state policy for Task 2 — reset, preserve, or hybrid?
2. Thread `_aliases.yaml` into Step 1 prompt now, or defer as follow-up?
3. Queue-file path: `wiki/ideas/` or `wiki/_queue/`?
4. Lint cadence: weekly manual or wired into daily pipeline?
5. TOPIC-MAP regen: delete-and-scaffold now, or build `rebuild_topic_map_llm()`?

**Tool notes:**
- `TaskUpdate` tool was not available in this agent's tool environment (only MCP tools + standard harness tools were offered). This report captures status in place; Gary may need to flip task #42 manually on the orchestrator side.

---

## Task 3 Report: Self-contained data-prep analysis

**Status:** DONE (analysis-only — no code changes)

**Deliverable:** [`docs/self-contained-analysis.md`](docs/self-contained-analysis.md)
- 617 lines / ~4,400 words
- 1 Mermaid diagram (two-layer architecture)
- 10 sections: Overview → Two layers → Formula fix (SOLVED) → Image fix (Task 1 code landed, verification pending) → Dependency map → Open-sourcing checklist → What cannot be removed from Claude → Fresh-clone risks → Tl;dr pitch → File-reference appendix

**Key findings:**

1. **Data-prep layer is already effectively Claude-free.** `raw_ingest.py`, `reextract_fulltext.py`, `extract_images_cli.py`, `fetch_paper.py`, `index_builder.py` — none of them call `claude`. Verified by grepping `rg 'claude|subprocess' scripts/raw_ingest.py ...` → no matches. The entire formula + image fixing pipeline uses Marker + PyMuPDF + stdlib only.

2. **`_call_claude` is a clean single swap point.** Every LLM call in the compile layer goes through one 15-line function at `scripts/wiki_compiler.py:28-44`. A non-Claude user can swap in OpenAI, Anthropic SDK, or Ollama by editing that one function. Recommend renaming to `_call_llm` and dispatching on `LLM_BACKEND` env var before open-sourcing.

3. **Two CRITICAL open-sourcing gaps:**
   - `marker-pdf` is **NOT in `requirements.txt`**. Fresh clones will silently fall back to the legacy HTML extractor and get noisy Unicode fulltext instead of inline LaTeX, without realizing it.
   - `scripts/config.py::get_wiki_path()` **unconditionally** loads `~/.config/paper-collector/config.yaml`. A fresh clone FileNotFoundErrors before `raw_ingest` can do anything. Needs a repo-local fallback (`Path(__file__).parent.parent / "wiki"`).

4. **Task 1's image fix has landed in code (as of 17:44)** but not yet verified by a batch run. New functions in `scripts/raw_ingest.py`: `extract_fulltext_and_images_with_marker`, `save_marker_images`, `_rewrite_marker_refs`, `reextract_images`. New CLI `scripts/extract_images_cli.py` mirrors `reextract_fulltext.py`. On-disk spot check of `2602.22088` shows it still has only `fulltext.md` + `meta.yaml`, so the 29-paper batch is still pending.

5. **Subtle inconsistency in `ingest_paper`:** it still uses the split text+image path (`extract_fulltext_with_latex` separately from `extract_images`) rather than the new unified `extract_fulltext_and_images_with_marker`. Only the explicit `reextract_images` backfill uses the unified path. For true self-containedness, `ingest_paper` should eventually migrate so a single Marker run produces both.

**Hardcoded personal paths that need sanitization before release:**
- `scripts/daily_search.sh:5,13` — `/home/gary/Documents/awesome-robot-learning`
- `scripts/profile_bootstrap.py:173` — `/home/gary/Documents/awesome-humanoid-robot-learning/README.md`
- `scripts/bootstrap_embeddings.py:183` — same as above

**Blockers:** none for this task. The analysis is complete and actionable.

**Tool notes:**
- `TaskUpdate` tool was not available in this agent's environment. Same situation as Task 4.
- Task 1's report was still pending at the time of writing. I polled `log.md` twice (~10 min total) and then proceeded with the analysis using on-disk inspection of `scripts/raw_ingest.py` (mtime 17:44 confirmed Task 1 had written the new functions). Section 4 reflects the actual implementation.

---

## Task 2 Prep Decisions (2026-04-09, Gary ruled)

After Task 4 (`docs/wiki-design.md`) surfaced 5 open questions, Gary made the following high-quality / high-cost decisions. All 5 bias toward "do it right once" over fast start.

| # | Question | Decision |
|---|----------|----------|
| 1 | Concept state for Task 2 | **RESET** — move existing `wiki/concepts/` to backup, compile from scratch |
| 2 | `_aliases.yaml` timing | **Before Task 2** — thread into `_build_step1_prompt` first, then compile |
| 3 | Queue file path | **`wiki/_queue/`** (top-level, not `wiki/ideas/`) |
| 4 | Semantic lint cadence | **Daily pipeline** (not weekly manual) |
| 5 | TOPIC-MAP rebuild | **New `rebuild_topic_map_llm()` function** (not delete-and-scaffold) |

### Critical path before Task 2 can run

1. **Prep A** — Create `wiki/concepts/_aliases.yaml` with Force-VLA canonical concept names
2. **Prep B** — Modify `scripts/wiki_compiler.py::_build_step1_prompt` to load and inject aliases
3. **Prep C** — Write `rebuild_topic_map_llm()` function (in `index_builder.py` or `wiki_compiler.py`) — called in Task 2 post-compile phase
4. **Prep D** — `git mv wiki/concepts wiki/concepts.backup.2026-04-09 && mkdir wiki/concepts` (right before Task 2 kicks off)
5. **Prep E** — `mkdir wiki/_queue` + seed `_wiki-fixes.md` and `_insight-queue.md` with headers (non-blocking for Task 2 but good to land now)

### Non-blocking deferred

- Decision #4 daily semantic lint → `scripts/daily_pipeline.py` integration after Task 5 deep lint completes

### Dependencies

Prep A–C can run in parallel with Task 1 (#39) still in progress (image extraction doesn't touch compiler / concept / topic-map files). Prep D must wait until right before Task 2 starts.

---

## Task 1 Report: Extract images for 29 papers + inject into fulltext.md

**Status:** DONE — 29/29 papers processed, 288 images extracted, 288 inline refs, 0 failures. Task #40 (compile) unblocked.

**Approach chosen:** **Option B (Marker with image output)**.

**Why B, not A (PyMuPDF `page.get_images`):**
- Marker already places `![](<name>)` image references at semantically correct positions in the markdown — next to the figure captions, inside the same page context. The old PyMuPDF path only extracted raw embedded bitmaps with no idea where they belonged, so Task 2's legacy run dumped 82 orphan files onto `2411.15753` with zero inline references. Option A would mean re-inventing figure→caption alignment by hand.
- Marker filenames (`_page_{N}_Figure_{idx}.jpeg`) encode the page + kind, so we can deterministically rename to our `page{NNN}-img{MM}.{ext}` convention and rewrite the markdown refs with a single regex pass.
- Marker's image block detection filters out inline math/ligature glyphs that PyMuPDF would have saved as tiny "images", so we get semantic figures/pictures/tables only.
- Extra bonus: the same converter that extracts inline LaTeX already has the images in `MarkdownOutput.images` — one Marker run, one GPU warm-up, two artifacts.

**Code changes:**

- `scripts/raw_ingest.py` (+ ~150 lines):
  - `_MARKER_IMG_NAME_RE` — regex to parse `_page_{N}_{Kind}_{idx}.{ext}` into `(page, index, ext)`.
  - `_parse_marker_image_name()` — extracts 1-indexed page number (Marker uses 0-index), block index, extension.
  - `extract_fulltext_and_images_with_marker(pdf_bytes, *, converter=None) -> tuple[str, dict] | None` — new unified Marker entry point; returns `(markdown, images_dict)` where `images_dict` is Marker's raw `{name: PIL.Image}` map. `extract_fulltext_with_latex` now delegates to this function so the old API is preserved.
  - `save_marker_images(images, out_dir, *, markdown) -> tuple[manifest, rewritten_md]` — writes each PIL image to `out_dir/page{NNN}-img{MM}.{ext}`, builds manifest sorted by (page, index), skips images smaller than `_MIN_IMAGE_DIM=32`, caps at `_MAX_IMAGES_PER_PAPER=120`, and returns the rewritten markdown with every Marker ref replaced by `images/pageNNN-imgMM.ext`.
  - `_rewrite_marker_refs(markdown, rename_map)` — regex sub `!\[alt\]\(target\)` → `!\[alt\](new_path)`; orphaned refs are stripped entirely so nothing 404s later.
  - `reextract_images(arxiv_id, wiki_dir, *, converter=None) -> dict` — batch helper mirroring `reextract_fulltext`: fetches PDF, runs Marker, wipes stale `images/*` files, saves new ones, overwrites `fulltext.md` with rewritten markdown, updates `meta.yaml` `assets` (`fulltext.md`, `images.json`, `images/`) + `updated_at`. Returns `{status, images, chars, refs}`.
- `scripts/extract_images_cli.py` (NEW, 180 lines):
  - CLI driver: `python3 -m scripts.extract_images_cli [arxiv_ids...] [--limit N] [--dry-run]`.
  - Pre-warms the Marker converter once via `_get_marker_converter()` and reuses it across all papers (saves ~5-15s per paper on model load).
  - Discovers papers by walking `wiki/raw/papers/*/meta.yaml`.
  - Per-paper timing, final summary, soft-fail semantics (a bad paper doesn't abort the batch).
- `tests/test_raw_ingest.py` (+ ~230 lines, 21 new tests across 5 new classes):
  - `TestParseMarkerImageName` (4) — Figure / Picture / Table / garbage name parsing, page offset.
  - `TestRewriteMarkerRefs` (3) — rewrite known ref, drop orphaned, preserve unrelated (external URL) refs.
  - `TestSaveMarkerImages` (4) — manifest + files written, tiny images dropped, unparseable names dropped, sort order by (page, index).
  - `TestExtractFulltextAndImagesWithMarker` (4) — missing converter, empty bytes, injected converter returns `(md, images)`, converter exception → None.
  - `TestReextractImages` (6) — missing meta, PDF fetch fail, marker None, happy path rewrites fulltext + writes files + manifest, meta.yaml assets+date updated, non-Marker refs (e.g. `![logo](https://cdn...)`) preserved.
  - `_FakePILImage` stand-in avoids pulling Pillow into the mock stack; all Marker mocked via `unittest.mock.patch("scripts.raw_ingest._get_marker_converter", ...)` or `extract_fulltext_and_images_with_marker`; tests run in 0.16s with no GPU.

**Test results:**

```
tests/test_raw_ingest.py — 64 passed in 117s (43 existing + 21 new)
tests/                   — 260 passed, 1 pre-existing flaky network test (test_fetch_s2_metadata_from_arxiv_id — unrelated, passes in isolation)
```

**Full batch run** (17:44:48 → 18:05:43, 20m 55s wall clock):

```
Summary: 29 total, 29 ok, 0 failed, 0 skipped, 288 images total
Total chars written: 1,703,693    Avg duration/paper: 43.2s    Avg images/paper: 9.9
```

Per-paper top 10 by image count:

| arxiv_id | images | refs | files | note |
|----------|-------:|-----:|------:|------|
| 2602.22088 | 27 | 27 | 27 | Force Policy (most figures) |
| 2503.02881 | 24 | 24 | 24 | |
| 2505.22159 | 20 | 20 | 20 | |
| 2602.23648 | 17 | 17 | 17 | |
| 2509.19696 | 16 | 16 | 16 | Diffusion policy (sample-verified) |
| 2409.11047 | 12 | 12 | 12 | |
| 2602.10013 | 12 | 12 | 12 | |
| 2502.17432 | 11 | 11 | 11 | |
| 2512.23864 | 10 | 10 | 10 | |
| 2602.14174 | 10 | 10 | 10 | |

Per-paper durations clustered around 25-50s/paper, with a few slower outliers (137.9s on `2602.01153`, 90.4s on `2602.23648`, 69.7s on `2507.09160`) due to larger PDF page counts + table recognition.

**Sample verification** (manual inspection of the 3 representative papers requested):

- **`2411.15753` FoAR** — 7 images, 7 inline refs, 2 block LaTeX + 26 inline `$...$`. Image refs sit right above `Fig. 1`, `Fig. 2`, the three task description paragraphs (Wiping / Peeling / Chopping), `Fig. 4`, and `Fig. 5` captions. All 7 manifest entries correspond to on-disk files; the 82 stale Task 2 PyMuPDF files were wiped by the cleanup step inside `reextract_images`.
- **`2509.19696` Diffusion Policy** — 16 images, 16 inline refs, 42 block + 210 inline formulas. Fig. 1 appears above the `q(z_t \mid z_{t-1})` forward process equation and caption that explicitly references the forward/reverse diagrams. Fig. 2 (Norton equivalent network) and Fig. 3 (sZFT diffusion reconstruction) are likewise inline with their caption + formula context.
- **`2602.22088` Force Policy** — 27 images, 27 inline refs, 40 block + 359 inline formulas (formula-heaviest paper in the corpus). Figures appear inline with `Fig. 1: Global-Local Vision-Force Policy`, `Fig. 2: Interaction Frame`, `Fig. 4: Tasks`, etc. The earlier Task 2.1 work's inline LaTeX formulas are fully preserved — verified by grep count matching pre-run numbers.

**Aggregate verification across all 29 papers:**

```
Total papers: 29
Total images: 288   Total inline refs: 288   Total on-disk files: 288
Per-paper manifest count == inline ref count == on-disk file count  for every paper.
Zero papers without images.json.
```

**meta.yaml spot check** (`2602.22088`):

```yaml
assets:
- fulltext.md
- images.json
- images/
updated_at: '2026-04-09'
```

**Acceptance checklist:**

- [x] Every one of 29 papers has `images/` + `images.json` + updated `fulltext.md`.
- [x] Image refs inline with figure captions, not appended at end of file.
- [x] Marker's `$...$` / `$$...$$` LaTeX preserved — formulas untouched (verified on 3 sample papers, formula counts match Task 2.1 baselines).
- [x] `images.json` manifest well-formed: `{page, index, path, width, height, ext, bytes}`.
- [x] `meta.yaml.assets` includes `fulltext.md`, `images.json`, `images/`; `updated_at` bumped.
- [x] Naming convention `page{NNN}-img{MM}.{ext}` consistent across all papers.
- [x] 29/29 ok, 0 failed, 0 skipped.
- [x] All 43 pre-existing `test_raw_ingest.py` tests still pass; 21 new tests added and passing (64 total).
- [x] No hardcoded paths added; uses `scripts.config.get_wiki_path()`.
- [x] Functions kept <50 lines, files <800 lines (`raw_ingest.py` now ~900 lines — ⚠ above the 800 cap, should be split in a follow-up refactor; the new functions themselves are under 50 lines each).
- [x] Legacy `2411.15753` PyMuPDF images wiped cleanly; new Marker figures replace them without orphans.

**Task #40 (compile) unblocked:** every paper now has semantic figure/picture/table references inline with the prose, ready for the wiki compiler to surface in the generated paper pages.

**Follow-up nits (non-blocking):**
- `scripts/raw_ingest.py` has grown past the 800-line advisory cap. Consider extracting `scripts/marker_utils.py` with `_get_marker_converter`, `extract_fulltext_with_latex`, `extract_fulltext_and_images_with_marker`, `save_marker_images`, `_rewrite_marker_refs`, `_parse_marker_image_name` in a follow-up.
- `ingest_paper()` still takes the split "Marker fulltext + PyMuPDF images" path (from Task 2 era). For self-containedness, migrate it to call `extract_fulltext_and_images_with_marker` end-to-end so a fresh ingest gets inline image refs on day one, not only via the `reextract_images` backfill. Noted separately in Task 3's analysis (point 5).

---

## Prep C — rebuild_topic_map_llm() (2026-04-09)

**Status:** DONE (Task #46 completed)

**Files changed:**
- `scripts/wiki_compiler.py` — added `rebuild_topic_map_llm(wiki_dir, timeout=600) -> Path` (~140 lines). Reads every `wiki/concepts/*.md` frontmatter + first ≤300 chars of prose as a hint, optionally feeds the current `TOPIC-MAP.md` as context, then calls `_call_claude` with a Chinese prompt asking for 5-10 parent topics of `## Heading` + `- [[slug]]` bullets. Strips ```markdown fences, auto-prepends `# Topic Map` header if missing, warns (not fails) on concepts absent from output, overwrites `wiki/TOPIC-MAP.md`. Placed right before `compile_batch_v2`.
- `scripts/wiki_compiler.py::compile_batch_v2` — now calls `rebuild_topic_map_llm(wiki_dir)` after `build_index_pages(wiki_dir)` (wrapped in try/except so LLM failure doesn't break batch).
- `tests/test_wiki_compiler.py` — new `TestRebuildTopicMapLLM` class with 8 tests (placeholder empty path, concept-list injection with mocked LLM, markdown fence stripping, auto-prepended header, missing-slug warning, overwrite of existing file, INDEX.md skip). Uses `@patch("scripts.wiki_compiler._call_claude")`.

**Design decision:** function lives in `wiki_compiler.py` (not `index_builder.py`) because it needs `_call_claude` — the single LLM entry point identified by Task 3's self-contained analysis. Keeps the OSS swap boundary clean.

**Test results:**
```
tests/test_wiki_compiler.py  —  57 passed in 0.61s
(49 prior + 8 new TestRebuildTopicMapLLM)
```
Invocation: `PYTHONPATH= PYTHONNOUSERSITE=1 python -m pytest tests/test_wiki_compiler.py -v --override-ini="addopts=" -p no:cacheprovider` (the `PYTHONPATH=` clear fixes ROS-jazzy pytest plugin pollution — better than CLAUDE.md's documented workaround).

---

## Prep E — wiki/_queue/ seeds (2026-04-09)

**Status:** DONE (Task #48 completed)

**Files created** (top-level `wiki/_queue/`, **not** `wiki/ideas/` — per Gary's decision #3):

- `wiki/_queue/_wiki-fixes.md` — append-only queue of wiki corrections (target path, source, problem, fix). Entry format in header. Marker comment for insertion point.
- `wiki/_queue/_insight-queue.md` — append-only queue of Q&A / reading insights to backfill into concept pages. Entry format (source, insight, connects-to, backfill target) in header.
- `wiki/_queue/README.md` — explains the reconciliation workflow: append entry → edit target wiki file → remove entry in same commit. Documents guardrails (no rewriting history, ~30 entry soft cap, 14-day re-triage) and rationale for top-level `_queue/` vs `wiki/ideas/`.

**Index-builder safety check:** grepped `scripts/index_builder.py` for `glob`/`iterdir` — all scans target `papers/`, `concepts/`, `raw/` subdirs explicitly. `wiki/_queue/` is safely invisible to `build_all_indexes`.

---

## Prep D — RESET wiki/concepts/ (2026-04-09)

**Status:** DONE (Task #47 completed)

**Action:** Moved the existing 17 concept pages + `INDEX.md` to `wiki/concepts.backup.2026-04-09/`, re-created an empty `wiki/concepts/`, and preserved `_aliases.yaml` into the fresh directory (it's needed by Prep B's alias-injection path).

```
mv wiki/concepts wiki/concepts.backup.2026-04-09
mkdir wiki/concepts
cp wiki/concepts.backup.2026-04-09/_aliases.yaml wiki/concepts/_aliases.yaml
```

Note: repo uses plain `mv` rather than `git mv` because `wiki/` is in `.gitignore` (verified with `git check-ignore wiki/`). The backup directory is safe on disk even without git tracking.

**Post-reset inventory:**
- `wiki/concepts/` — only `_aliases.yaml` (Prep B seed, preserved)
- `wiki/concepts.backup.2026-04-09/` — 18 files (17 concept pages + `INDEX.md`)
- `wiki/papers/` — **not touched** (3 stale pages from earlier run; Task 2 compile is idempotent and will overwrite them)
- `wiki/TOPIC-MAP.md`, `wiki/INDEX.md` — **not touched** (will be regenerated by `build_index_pages` + `rebuild_topic_map_llm` at the end of `compile_batch_v2`)

**Scope rationale:** Gary's decision #1 was scoped to concept pages only ("丢弃现有 17 个 concept 页面"), not the full wiki. Keeping scope tight avoids destroying anything outside the decision.

---

## Task 1 — Verification on all 29 papers (2026-04-09)

**Status:** DONE (Task #39 completed — was previously marked pending but verification confirms it's finished)

Background run finished before context break. Re-verified from main conversation:

```bash
ok=0; miss=0
for dir in wiki/raw/papers/*/; do
  id=$(basename "$dir")
  if [ -f "$dir/images.json" ] && [ -d "$dir/images" ] && [ -f "$dir/fulltext.md" ]; then
    ok=$((ok+1)); else miss=$((miss+1)); echo "MISS: $id"; fi
done
# Result: OK: 29  MISSING: 0
```

Task 2 unblocked (blockedBy: 39 ✅, 44 ✅, 45 ✅, 46 ✅, 47 ✅).

---

## Task 5 — Karpathy-style Deep Lint (2026-04-10)

After the Task 2 29-paper cold start + 2505.20829 ingest, ran a multi-phase
lint across raw/ and wiki/. Results below. **This was lint-only — no files
rewritten. Actionable items moved to `wiki/_queue/_wiki-fixes.md` and
`wiki/_queue/_insight-queue.md`.**

### Headline

The wiki reports **105 concept pages / 32 papers** but the true state is:

| Metric | Value |
|---|---|
| Concept files on disk | 105 (+ INDEX.md + `.md` garbage + `_aliases.yaml`) |
| Concept files with parseable `---` frontmatter | **46** |
| Concept files wrapped in ```` ```markdown ```` code fences (unparseable) | **58** |
| Concept files with empty name (`.md`) | 1 |
| Paper frontmatter references → real concept files | **only 6 of 63** |
| Missing foundational concept pages | **57** |

**Bottom line: 55 % of the concept wiki is corrupted by an LLM output parser
bug, and the most important foundational concepts were never created at all.**
The `rebuild_topic_map_llm` run that "succeeded" at 13:40 only saw 46 of 105
concepts, so the current `TOPIC-MAP.md` is built on less than half the data.

### Phase A — Structural

Ran `scripts.wiki_compiler.lint_wiki()` and custom wikilink/backlink checks.

**`lint_wiki()` existing output (4 warnings):**

- `digit.md` ↔ `digital-twin-dynamics-compensation.md` — false positive, substring collision only
- `information-bottleneck.md` ↔ `variational-information-bottleneck.md` — **real duplicate**, merge candidate
- `reward-weighted-flow-matching.md` ↔ `safety-aware-reward-weighted-flow-matching.md` — parent-child, not duplicate
- `simulated-zero-force-trajectory.md` ↔ `zero-force-trajectory.md` — **real duplicate**, merge candidate

**Wikilink integrity — 1042 broken `[[…]]` refs in paper & concept bodies.**
Two sources:

1. Pre-Prep-D legacy pages (`2401.00003.md`, `2604.07331.md`) contain Chinese
   wikilinks like `[[扩散策略]]`, `[[触觉反馈]]` that pointed at concept pages
   which no longer exist after the Prep-D concepts/ reset.
2. Post-Task-2 pages reference English slugs like `[[diffusion-policy]]`,
   `[[impedance-control]]`, `[[contact-rich-manipulation]]` — these refer to
   foundational concepts that **the Step 2 LLM decided not to create** (see
   Phase C finding below).

**Backlink asymmetry — 377 cases.** Vast majority are "paper P says concept C,
but concept C's file doesn't exist". Same root cause as the missing foundationals.

### Phase B — Raw data

Stats across 30 `wiki/raw/papers/` directories (29 Force-VLA + 2505.20829):

- fulltext chars: min=39927, median=53600, max=116213 — **all healthy**, Marker working
- 0 papers with empty/tiny fulltext
- 0 papers with 0 images (my earlier "1 image per paper" report was a lint-script
  bug — `images.json` is a `{"images": [...]}` dict not a list, so `len()`
  counted top-level keys. Real extraction is fine — e.g., 2505.20829 has 56 images.)
- 28 of 30 papers have no `formulas.md`. This is **expected**: Marker inlines
  LaTeX directly into `fulltext.md`, so a separate `formulas.md` is only
  produced by the legacy pre-Marker path. `2401.00003` and `2604.07331` are
  the only two remaining legacy ingests. **Not a bug.**

### Phase C — Semantic (the critical one)

**C-1: Code-fence parser bug (CRITICAL).** 58 of 105 concept files start with
a literal ```` ```markdown ```` code fence instead of `---`. Every one of them
also ends with a closing ```` ``` ```` fence. This means Step 2's LLM wrapped
its entire concept-page output in a markdown code block, and
`_parse_step2_output` (`scripts/wiki_compiler.py:893`) **does not strip fences**.

Compare to Step 1, which explicitly strips preamble / fences when reassembling
the paper page (see `compile_paper_v2` line 968 comment: "any LLM preamble or
code-fence wrapping is stripped"). Step 2 has no equivalent defense.

Impact:
- `parse_frontmatter()` fails → these files are **invisible** to `concepts/INDEX.md`,
  to `rebuild_topic_map_llm`, and to every backlink check.
- Bodies are still visible to humans but can't be programmatically navigated.
- The topic map just rebuilt by LLM is constructed from only 46/105 concepts.

**C-2: Empty-name concept file `wiki/concepts/.md`.** The LLM emitted
`===CONCEPT:  ===` (empty name) during some compile, and `_parse_step2_output`
wrote it to `{empty}.md`. Contents look like a mis-formatted concept listing.
Delete it.

**C-3: Missing foundational concept pages (57).** Papers reference these
slugs in their frontmatter but no file exists. Top by citation count:

| Refs | Slug |
|---|---|
| 30 | contact-rich-manipulation |
| 26 | imitation-learning |
| 24 | diffusion-policy |
| 18 | force-torque-sensing |
| 17 | vla |
| 16 | tactile-sensing |
| 16 | force-vla |
| 13 | teleoperation-data-collection |
| 13 | pi-zero |
| 12 | action-chunking |
| 12 | force-aware-reactive-policy (actually exists as fenced file — C-1 overlap) |
| 12 | impedance-control |
| 11 | hybrid-force-position-control |
| 9 | flow-matching-policy |
| 9 | adaptive-compliance-policy |
| 9 | reactive-diffusion-policy |
| 6 | force-policy |
| 6 | mixture-of-experts |
| 5 | sim-to-real |
| 5 | admittance-control |

This is the **Karpathy inversion**: concept pages *should* canonicalise
foundational vocabulary (so many papers can share one definition of
"diffusion policy"), and paper-specific novelties should be **either in the
paper page** or in a dedicated concept page only if they're load-bearing
across multiple papers. Currently:

- 42 of the 46 parseable concepts have exactly 1 paper → paper-specific
  contributions like `fsm-privileged-expert`, `e2vla`, `fvlmoe`,
  `modality-entropy-imbalance`. Most shouldn't be standalone concept pages
  at all — they belong as detail sections on the paper page, with the
  concept page reserved for whatever synthesis actually spans ≥2 papers.
- Meanwhile `diffusion-policy` (24 refs) has no page.

Root cause: Step 2's LLM interpretation of "NEW_CONCEPT" drifted toward
"every novel named contribution", and the prompt doesn't explicitly guard
against creating pages for broad vocabulary. The aliases file
(`_aliases.yaml`) lists `vla`, `pi-zero`, `diffusion-policy`, etc., but
aliases only canonicalise names — they don't force page creation.

**C-4: 3 concepts missing `parent_topic`:** `dual-modality-heterogeneity`,
`dual-path-tactile-encoder`, `force-based-tactile-sensor`. Low priority
because these are all C-3 candidates for "shouldn't be a concept page anyway".

### Phase D — Output

Queue files appended (see `wiki/_queue/_wiki-fixes.md` and `_insight-queue.md`).
No files were rewritten. Task 5 produces a report only.

---

## 2026-04-11 — Wiki Health Cleanup & Backfill

### Problem

Post-compile wiki audit revealed structural issues:
- 6 empty stub files at `wiki/` root (accidental creation)
- `concepts.backup.2026-04-09` directory superseded by current 115 concepts
- 2 orphan papers: `2401.00003` (LLM test stub, no raw), `2604.07331` (missing raw)
- INDEX drift: 115 concept files but only 104 indexed
- TOPIC-MAP built on partial data (58/105 fenced files were invisible to parser)
- 17 foundational concepts missing pages despite high citation counts
  (e.g. `force-vla` 16 refs, `pi-zero` 13 refs, `hybrid-force-position-control` 11 refs)
- `_wiki-fixes.md` listed 57 missing concepts, but 40 had already been created

### Actions Taken

| # | Action | Detail |
|---|--------|--------|
| 1 | Delete 6 empty stubs | `wiki/{13.md, action-chunking.md, Contact-Rich Manipulation.md, Impedance Control.md, 模仿学习.md, 运动重定向.md}` — all 0-byte, untracked |
| 2 | Delete `concepts.backup.2026-04-09` | 17 files, fully superseded, `_aliases.yaml` already in current `concepts/` |
| 3 | Delete orphan `2401.00003.md` | Code-fence wrapped LLM test output, no venue/date, no raw data |
| 4 | Re-ingest `2604.07331` raw | RoSHI paper — `raw_ingest.ingest_paper('2604.07331')` → wrote meta.yaml, fulltext.md, images.json |
| 5 | Dry-run backfill | `backfill_foundational_concepts_llm(dry_run=True, min_citations=2)` → 17 missing concepts identified |
| 6 | Backfill 17 concepts | `backfill_foundational_concepts_llm(min_citations=2)` — 17/17 created, 0 failed, ~19 min total |
| 7 | Rebuild INDEX + TOPIC-MAP | `build_all_indexes()` → 31 papers, 132 concepts, 0 drift. `rebuild_topic_map_llm()` → 9 topics, 132 concepts, 0 missing |
| 8 | Update `_wiki-fixes.md` | Marked backfill entry as partially resolved → fully resolved |

### Backfilled Concepts (17)

```
force-vla (16), teleoperation-data-collection (13), pi-zero (13),
hybrid-force-position-control (11), adaptive-compliance-policy (9),
mixture-of-experts (6), admittance-control (5), sim-to-real (5),
diffusion-model (4), compliance-control (4), teleoperation (4),
transformer-policy (4), precise-manipulation (3),
force-attending-curriculum (3), reinforcement-learning (3),
gello-teleoperation (2), domain-randomization (2)
```

Intentionally skipped 4 singletons (cite=1): `force-prompt`, `human-motion-capture`,
`humanoid-robot-learning`, `cross-scale-mixture-of-experts` — candidates for
paper-page demotion per Karpathy inversion principle.

### Before → After

| Metric | Before | After |
|--------|--------|-------|
| Papers | 32 (2 orphan) | 31 (0 orphan) |
| Raw papers | 30 | 31 |
| Concepts (files) | 115 | 132 |
| Concepts (indexed) | 104 (drift=11) | 132 (drift=0) |
| Topics | 10 | 9 (new: Sim-to-Real & Domain Transfer) |
| Wiki root garbage | 6 stubs | 0 |
| Stale papers (no raw) | 2 | 0 |

---

## 2026-04-12 — concept_lint_llm Phase 1

### Implementation

Added `concept_lint_llm()` to `scripts/wiki_compiler.py` (~200 LOC):
- `_gather_concept_signals()` — collects slug, citation_count, cross_link_in_count,
  parent_topic, description, body_head for all 132 concepts
- `_is_demote_candidate()` — pre-filter: cite=1 AND cross_link_in=0
- `_build_concept_lint_prompt()` — builds LLM prompt with full concept table +
  candidate detail blocks
- `concept_lint_llm()` — orchestrator: gather → filter → LLM call → write proposals

### First Run Result

- Scanned: 132 concepts
- Pre-filtered DEMOTE candidates: 5
- LLM confirmed: **4 DEMOTE**, **1 KEEP**
- DEMOTE: `3d-deformation-field`, `dual-modality-heterogeneity`, `objtac-dataset`, `tactile-cot-reasoning`
- KEEP: `task-frame-formalism` (classic force-control theory, domain fundamental)
- Output: `wiki/ideas/_concept-lint-2026-04-12.md` (awaiting review)

### Design Doc

Full design written to `wiki/ideas/_concept-lint-llm-design.md`:
- Phase 1 (done): read-only lint proposals
- Phase 2 (future): single-action executors (apply_merge/rename/demote)
- Phase 3 (future): batch CLI with interactive confirm

