# Project Architecture Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a private `projects/` submodule and migrate `force-control-policy` out of `wiki/ideas/`, establishing the wiki-vs-projects separation defined in `docs/superpowers/specs/2026-04-17-project-architecture-design.md`.

**Architecture:** Create a new private GitHub repo `awesome-robot-learning-projects`, register it as a second git submodule alongside the existing `wiki/`. Populate it with conventions (INDEX, README, TEMPLATE) and migrate the one existing active project. Leave a one-line tombstone behind in `wiki/ideas/` and update the mother repo's `CLAUDE.md` navigation protocol.

**Tech Stack:** git, git submodules, `gh` CLI (GitHub), Markdown.

**Prerequisites:**
- `gh` CLI authenticated as `Garyandtang` (verified: `repo` scope present)
- Clean mother repo (unrelated work-in-progress modifications on `scripts/*`, `data/*`, `wiki` pointer exist but won't be touched — do not stage them during this plan)
- Conventional remote URL format matches existing wiki submodule: `git@github.com:Garyandtang/awesome-robot-learning-projects.git`

---

## File Structure

### New files (mother repo)
- `.gitmodules` (modified): adds the `projects` submodule entry
- `CLAUDE.md` (modified): navigation protocol covers both submodules

### New files (`projects/` submodule)
- `projects/README.md` — conventions summary
- `projects/INDEX.md` — global project index table
- `projects/TEMPLATE/plan.md` — plan template (copy-to-new-project)
- `projects/TEMPLATE/log.md` — log template
- `projects/TEMPLATE/experiments/.gitkeep`
- `projects/force-control-policy/plan.md` — migrated (stripped of Discussion Log)
- `projects/force-control-policy/log.md` — empty skeleton
- `projects/force-control-policy/discussion.md` — extracted Discussion Log from source
- `projects/force-control-policy/experiments/.gitkeep`

### Modified files (`wiki/` submodule)
- `wiki/ideas/force-control-policy-plan.md` — replaced with one-line tombstone

---

## Task 1 — Create Private GitHub Remote

**Files:**
- None local; creates remote only

- [ ] **Step 1.1: Create the private repo via `gh`**

```bash
gh repo create Garyandtang/awesome-robot-learning-projects \
  --private \
  --description "Private: research project plans, logs, and experiment records (companion to awesome-robot-learning-wiki)" \
  --clone=false
```

Expected: `✓ Created repository Garyandtang/awesome-robot-learning-projects on GitHub`

- [ ] **Step 1.2: Verify remote exists and is private**

```bash
gh repo view Garyandtang/awesome-robot-learning-projects --json name,visibility,url
```

Expected JSON includes `"visibility":"PRIVATE"` and correct URL.

- [ ] **Step 1.3: No commit — remote creation is an out-of-band action**

(Nothing to commit locally at this point. Proceed to Task 2.)

---

## Task 2 — Initialize `projects/` Submodule

**Files:**
- Modify: `.gitmodules`
- Create: `projects/` (submodule root)
- Create: `projects/INDEX.md`
- Create: `projects/README.md`

- [ ] **Step 2.1: Register the submodule in the mother repo**

```bash
cd /home/gary/Documents/awesome-robot-learning
git submodule add git@github.com:Garyandtang/awesome-robot-learning-projects.git projects
```

Expected: `Cloning into '.../projects'...` followed by an empty clone; `.gitmodules` gains a `[submodule "projects"]` entry.

- [ ] **Step 2.2: Verify `.gitmodules` now lists both submodules**

```bash
cat .gitmodules
```

Expected output:

```
[submodule "wiki"]
	path = wiki
	url = git@github.com:Garyandtang/awesome-robot-learning-wiki.git
[submodule "projects"]
	path = projects
	url = git@github.com:Garyandtang/awesome-robot-learning-projects.git
```

- [ ] **Step 2.3: Write `projects/README.md`**

Path: `projects/README.md`

```markdown
# Projects

> **Private** submodule for in-progress research work.
> Companion to `wiki/` (shareable received knowledge).

## What lives here

- `<slug>/plan.md` — forward-looking plan (计划书)
- `<slug>/log.md` — append-only implementation log
- `<slug>/experiments/YYYY-MM-DD-<name>.md` — one file per significant experiment
- `<slug>/discussion.md` — optional archived brainstorm history

## Conventions

- **slug**: kebab-case describing the research thrust, not a phase or version
  - Good: `force-control-policy`
  - Bad: `force-vla-phase0`, `rdp-v2`, `may-2026-run`
- **Status** (in `plan.md` frontmatter): `planning` → `active` → `paused` | `archived`
- **Cross-references**: projects may link into `[[wiki/concepts/...]]`, `[[wiki/papers/...]]`, `[[wiki/codebase/...]]`. The wiki **never** links back into projects (keeps the wiki publishable).
- **Log guardrail**: if `log.md` exceeds ~400 lines, cut a dated archive (`log-YYYY-QN.md`) and leave a pointer.

## New project

```bash
cp -r TEMPLATE <new-slug>
# then edit plan.md frontmatter and fill in content
```

## Index

See [`INDEX.md`](./INDEX.md).
```

- [ ] **Step 2.4: Write `projects/INDEX.md`**

Path: `projects/INDEX.md`

```markdown
# Projects Index

> Last updated: 2026-04-17

| Project | Status | Updated | TL;DR |
|---|---|---|---|
| _(none yet — first project added in Task 4)_ | | | |
```

- [ ] **Step 2.5: Commit scaffolding inside the submodule**

```bash
cd projects
git add README.md INDEX.md
git commit -m "chore: init projects submodule with conventions"
git push -u origin main 2>&1 || git push -u origin master
cd ..
```

Expected: initial commit pushed to `origin`. (If the default branch differs between `main`/`master`, the fallback `||` handles it. Check with `git branch --show-current` inside the submodule if unsure.)

- [ ] **Step 2.6: Commit the submodule pointer in the mother repo**

```bash
git add .gitmodules projects
git commit -m "chore: add projects submodule"
```

Expected: mother-repo commit referencing the new submodule at its initial commit.

- [ ] **Step 2.7: Verify**

```bash
git submodule status
```

Expected: two lines, one each for `wiki` and `projects`, both without `-` or `+` prefix (clean state).

---

## Task 3 — Add Project Templates

**Files:**
- Create: `projects/TEMPLATE/plan.md`
- Create: `projects/TEMPLATE/log.md`
- Create: `projects/TEMPLATE/experiments/EXAMPLE.md`

- [ ] **Step 3.1: Write `projects/TEMPLATE/plan.md`**

Path: `projects/TEMPLATE/plan.md`

```markdown
---
project: "<slug>"
title: "<one-sentence description of the thrust>"
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
status: "planning"   # planning | active | paused | archived
parent_topic: "<TOPIC-MAP path, e.g. Policy Architectures > Slow-Fast Policies>"
related_papers:
  - "<arxiv_id>"
related_concepts:
  - "<concept-slug>"
tags: []
---

# <Title>

> **TL;DR** — 3 sentences max: what this project is, why it's worth doing, what the intended artefact is.

## 1 Motivation
## 2 Hypothesis (falsifiable)
## 3 Prior Art Map
## 4 Approach Sketch
## 5 Success / Failure Criteria
> Include an MVE (minimum viable experiment) describing the cheapest first signal.
## 6 Risks
## 7 Next Actions
- [ ] A1: … (owner: gary, due: YYYY-MM-DD)
```

- [ ] **Step 3.2: Write `projects/TEMPLATE/log.md`**

Path: `projects/TEMPLATE/log.md`

```markdown
# <Project Name> — Implementation Log

> Append-only. Any granularity. For significant experiments, link out to `experiments/YYYY-MM-DD-<name>.md` rather than dumping here.

## YYYY-MM-DD — <one-line subject>

- **Where**: `<repo>@<commit>` or `projects/<slug>/code/<path>`
- **Did**: …
- **Result**: …
- **See**: [[experiments/YYYY-MM-DD-<name>]]
- **Notes**: …
```

- [ ] **Step 3.3: Write `projects/TEMPLATE/experiments/EXAMPLE.md`**

```bash
cd projects
mkdir -p TEMPLATE/experiments
```

Path: `projects/TEMPLATE/experiments/EXAMPLE.md`

```markdown
---
experiment: "<short-slug-matching-filename>"
date: "YYYY-MM-DD"
project: "<slug>"
status: "running"   # running | complete | aborted
---

# <Experiment title>

## Goal
> What single question does this experiment answer?

## Setup
- **Code**: `<external-repo>@<commit>` or `projects/<slug>/code/<path>`
- **Data**: <dataset name + version/split>
- **Hardware**: <GPU model / count / cluster>
- **Config**: <key hyperparams inline, or link to config file>

## Metrics (targets)
- <metric name> : <target threshold>

## Results
| Condition | <metric> | Notes |
|---|---|---|
|  |  |  |

## Interpretation
> What did the result tell us? Include the failure modes, not just the headline number.

## Next
- [ ] A1: …
```

- [ ] **Step 3.4: Commit templates inside submodule**

```bash
git add TEMPLATE/
git commit -m "chore: add project template (plan + log + experiment example)"
git push
cd ..
```

- [ ] **Step 3.5: Commit submodule pointer in mother repo**

```bash
git add projects
git commit -m "chore: bump projects submodule (add template)"
```

---

## Task 4 — Migrate `force-control-policy`

**Files:**
- Read: `wiki/ideas/force-control-policy-plan.md` (source)
- Create: `projects/force-control-policy/plan.md`
- Create: `projects/force-control-policy/discussion.md`
- Create: `projects/force-control-policy/log.md`
- Create: `projects/force-control-policy/experiments/.gitkeep`
- Modify: `projects/INDEX.md`

- [ ] **Step 4.1: Make the target directory**

```bash
cd /home/gary/Documents/awesome-robot-learning/projects
mkdir -p force-control-policy/experiments
touch force-control-policy/experiments/.gitkeep
```

- [ ] **Step 4.2: Extract the Discussion Log into `discussion.md`**

The source file `wiki/ideas/force-control-policy-plan.md` has section `## 9 讨论日志 / Discussion Log` at line 526 and next section `## 10 下一步行动 / Next Actions` at line 568. Lines 526–567 are the Discussion Log block.

```bash
cd /home/gary/Documents/awesome-robot-learning
sed -n '526,567p' wiki/ideas/force-control-policy-plan.md > projects/force-control-policy/discussion.md
```

Prepend a header so the extracted file stands on its own. Open `projects/force-control-policy/discussion.md` and insert at the top:

```markdown
# Force-Control Policy — Archived Brainstorm / Discussion Log

> Preserved from the original `wiki/ideas/force-control-policy-plan.md` on migration to projects/. Append new discussion in the project's `log.md` instead of here.

---
```

- [ ] **Step 4.3: Build `plan.md` by stripping the Discussion Log**

```bash
# Keep lines 1..525 (everything up through §8 Risks) AND 568..593 (§10 Next Actions + §附录)
head -n 525 wiki/ideas/force-control-policy-plan.md > projects/force-control-policy/plan.md
tail -n +568 wiki/ideas/force-control-policy-plan.md >> projects/force-control-policy/plan.md
```

Verify structure:

```bash
grep -n "^## " projects/force-control-policy/plan.md
```

Expected: section headings §1 through §8, then §10 and §附录. (No §9 Discussion Log.)

- [ ] **Step 4.4: Patch the plan's frontmatter**

Edit `projects/force-control-policy/plan.md` frontmatter:

- Replace `idea: "force-control-policy-plan"` → `project: "force-control-policy"`
- Update `updated: "2026-04-17"`
- Keep `status: active`
- Other fields (title, created, parent_topic, related_*, tags) stay as-is

Also: after the frontmatter, insert near the top (after TL;DR block):

```markdown
> **Discussion history**: see [`discussion.md`](./discussion.md) for the brainstorm log preserved from the wiki/ideas stage.
```

- [ ] **Step 4.5: Create empty `log.md`**

Path: `projects/force-control-policy/log.md`

```markdown
# Force-Control Policy — Implementation Log

> Append-only. Any granularity. For significant experiments, link out to `experiments/YYYY-MM-DD-<name>.md`.

## 2026-04-17 — project migrated out of wiki/ideas/

- Source: `wiki/ideas/force-control-policy-plan.md` (tombstoned)
- Plan + discussion split into separate files under `projects/force-control-policy/`
- No research work yet; first entry begins when α-1 baseline kicks off
```

- [ ] **Step 4.6: Update `projects/INDEX.md`**

Replace the empty row in `projects/INDEX.md`:

```markdown
# Projects Index

> Last updated: 2026-04-17

| Project | Status | Updated | TL;DR |
|---|---|---|---|
| [force-control-policy](./force-control-policy/plan.md) | active | 2026-04-17 | Force-aware slow-fast DP on X2Robot dual-arm + 6D F/T + Xense tactile; DP-level ablation before VLM backbone |
```

- [ ] **Step 4.7: Commit inside projects submodule**

```bash
cd projects
git add force-control-policy/ INDEX.md
git commit -m "feat: migrate force-control-policy from wiki/ideas/"
git push
cd ..
```

- [ ] **Step 4.8: Commit submodule pointer in mother repo**

```bash
git add projects
git commit -m "chore: bump projects submodule (first project: force-control-policy)"
```

- [ ] **Step 4.9: Verify structure**

```bash
ls projects/force-control-policy/
cat projects/INDEX.md
```

Expected: four entries (`plan.md`, `log.md`, `discussion.md`, `experiments/`); INDEX table includes force-control-policy row.

---

## Task 5 — Tombstone in `wiki/ideas/`

**Files:**
- Modify: `wiki/ideas/force-control-policy-plan.md` (reduced to a redirect stub)

- [ ] **Step 5.1: Replace content with a tombstone**

Path: `wiki/ideas/force-control-policy-plan.md` (full overwrite)

```markdown
---
idea: "force-control-policy-plan"
status: "promoted-to-project"
redirect: "projects/force-control-policy/"
moved_on: "2026-04-17"
---

# Moved → `projects/force-control-policy/`

This idea graduated out of the wiki on **2026-04-17**. The canonical plan, implementation log, and brainstorm history now live in the private `projects/` submodule.

- Plan: `projects/force-control-policy/plan.md`
- Log: `projects/force-control-policy/log.md`
- Discussion history (pre-migration): `projects/force-control-policy/discussion.md`

No further changes to this file. It exists only to keep old `[[force-control-policy-plan]]` links from 404-ing inside the wiki.
```

- [ ] **Step 5.2: Commit inside wiki submodule**

```bash
cd wiki
git add ideas/force-control-policy-plan.md
git commit -m "chore: tombstone force-control-policy-plan (moved to projects/)"
git push
cd ..
```

- [ ] **Step 5.3: Commit submodule pointer in mother repo**

```bash
git add wiki
git commit -m "chore: bump wiki submodule (tombstone force-control-policy)"
```

- [ ] **Step 5.4: Verify no broken references in wiki**

```bash
grep -rn "force-control-policy-plan" wiki/ --include="*.md"
```

Expected: matches only inside `wiki/ideas/force-control-policy-plan.md` (the tombstone itself). If other wiki files link to it, that's fine — the tombstone page keeps them working.

---

## Task 6 — Update `CLAUDE.md` Navigation Protocol

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 6.1: Read current CLAUDE.md to find insertion points**

```bash
grep -n "^## " CLAUDE.md
```

Expected sections include `Project Overview`, `Sections`, `Adding a Paper`, `Conda Environment`, `Scripts`, `Running Tests`, `Wordcloud Generation`, `Wiki Knowledge Base (Karpathy Method)`, `Commit Style`.

- [ ] **Step 6.2: Insert a new top-level section "Projects (Private Submodule)" right before "Commit Style"**

Content to insert:

```markdown
## Projects (Private Submodule)

`projects/` is a **private** git submodule companion to `wiki/`. It holds in-progress work — plans, implementation logs, experiment records — that belongs to gary, not to the shareable wiki.

### Directory layout

```
projects/
├── INDEX.md                 # Project index (status + TL;DR per project)
├── README.md                # Conventions
├── TEMPLATE/                # Copy-to-start-new-project
└── <slug>/
    ├── plan.md              # Forward-looking 计划书
    ├── log.md               # Append-only 实现记录
    ├── discussion.md        # Optional archived brainstorm history
    └── experiments/
        └── YYYY-MM-DD-<name>.md
```

### Navigation protocol (Q&A with both submodules)

For research-landscape questions (what does paper X claim, what is concept Y, how are topics organised): start in `wiki/`.

For "what is gary currently working on / what were the results of experiment Z / what's the next action on project P" questions: start in `projects/INDEX.md`, then drill into `projects/<slug>/{plan,log}.md` and relevant `experiments/`.

### Cross-reference rules

- `projects/` MAY link into `wiki/` using `[[wiki/concepts/<slug>]]`, `[[wiki/papers/<arxiv_id>]]`, `[[wiki/codebase/<slug>]]`.
- `wiki/` MUST NOT link back into `projects/`. Violating this pollutes the wiki's shareability.
- Within a project, relative links work: `[[experiments/2026-05-01-alpha1-baseline]]`.

### Slug convention

kebab-case describing the research thrust (not a phase or version). Examples: `force-control-policy`, `external-force-estimation`. Phase information lives inside `plan.md`.
```

Use Edit tool to place this block directly before the `## Commit Style` heading.

- [ ] **Step 6.3: Commit in mother repo**

```bash
git add CLAUDE.md
git commit -m "docs: document projects submodule in CLAUDE.md navigation"
```

---

## Task 7 — Final Verification

**Files:** (verification only; no writes)

- [ ] **Step 7.1: Both submodules clean and registered**

```bash
git submodule status
```

Expected: exactly two lines, neither prefixed with `+` (no drift) or `-` (uninitialised).

- [ ] **Step 7.2: Remote state matches local**

```bash
cd projects && git status && git log --oneline -5 && cd ..
cd wiki && git status && git log --oneline -3 && cd ..
```

Expected: each `git status` reports "up to date with origin" or equivalent; local log top matches what was pushed.

- [ ] **Step 7.3: Project discoverable via INDEX**

```bash
cat projects/INDEX.md
```

Expected: force-control-policy row present.

- [ ] **Step 7.4: Tombstone survives in wiki**

```bash
head -5 wiki/ideas/force-control-policy-plan.md
```

Expected: frontmatter with `status: "promoted-to-project"` and `redirect: "projects/force-control-policy/"`.

- [ ] **Step 7.5: Mother-repo log shows the migration arc**

```bash
git log --oneline -10
```

Expected (most recent first):
- `docs: document projects submodule in CLAUDE.md navigation`
- `chore: bump wiki submodule (tombstone force-control-policy)`
- `chore: bump projects submodule (first project: force-control-policy)`
- `chore: bump projects submodule (add template)`
- `chore: add projects submodule`
- `docs: add project architecture redesign spec`

- [ ] **Step 7.6: Summary to user**

Report back: what was created, what was moved, any anomalies (e.g., branch-name `main` vs `master` mismatch discovered in Step 2.5).

---

## Out of Scope (deferred)

These appear in the spec's Phase C / D but are NOT part of this plan:

- Migrating other `wiki/ideas/*` files (`external-force-estimation-survey.md` stays; `_concept-lint-*` → `docs/proposals/`).
- Cleaning up root-level `log.md`, `llm-knowledge-base-design.md`, `resume_cold_start.log`, `ingest_*.log`.
- `scripts/project_new.py` scaffolder.
- `scripts/project_index.py` index rebuilder.
- Slash commands for generating 计划书 / log entries.

Handle each when pressure arises for it.

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| `gh repo create` fails (network, auth, name collision) | Abort Task 1; user resolves remote state manually before retrying |
| Default branch in new repo is `main` vs. old `master` | Step 2.5 uses `main` first with `||` fallback to `master` |
| `sed` line-range extraction misses content if the source file was edited between plan-writing and execution | Step 4.3 includes a `grep` verification of section headings — if §9 is still present in `plan.md`, redo the split |
| Mother repo has unrelated WIP (taste_profile.yaml, scripts/*, wiki pointer drift) | All task commits use explicit `git add <path>` — no `git add -A`; WIP stays untouched |
| Force-control-policy plan references `[[force-control-policy-plan]]` or similar from other wiki pages that break | Step 5.4 greps to surface any such links; the tombstone page keeps them working |
