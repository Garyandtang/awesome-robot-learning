# Project Architecture Redesign — Separating Wiki (Learned) from Projects (Doing)

> Date: 2026-04-17
> Status: **APPROVED (verbal)** — awaiting user review of this written spec
> Author: gary + claude (brainstorming session)

## 1. Context & Problem

The repo's current layout grew organically and mixes two categorically different kinds of knowledge inside `wiki/`:

- **Received knowledge** — papers, concepts, external codebases, topic map. This is the wiki's original mission (Karpathy-style externalized memory for a stateless LLM).
- **In-progress work** — research plans, implementation records, experiment results. Currently squatting in `wiki/ideas/` and at the repo root (`log.md`, `llm-knowledge-base-design.md`).

Symptoms of the conflation:

1. `wiki/ideas/` holds three incompatible kinds of file: real projects (`force-control-policy-plan.md`), literature surveys (`external-force-estimation-survey.md`), and wiki infrastructure proposals (`_concept-lint-llm-design.md`).
2. `TEMPLATE.md` tries to stuff brainstorm + plan + execution into one file (via `Discussion Log`), which inevitably grows unwieldy once a project starts producing experiment results.
3. No place for implementation records (`实现记录`). Root `log.md` mixes agent-orchestration ops with research work. Daily `logs/*.log` are shell artefacts, not agent-readable notes.
4. The `wiki/` submodule signal ("this is shareable") is undermined by private in-progress work sitting inside it.
5. Update rhythms differ: wiki grows in occasional large chunks; project logs want almost-daily appends. Co-location produces noisy commit history on both sides.

## 2. Decisions (summary)

These were resolved during the 2026-04-17 brainstorming session:

| # | Question | Decision |
|---|---|---|
| Q1 | Idea vs. project granularity | **Per-project directory** (rejected single-file-per-idea) |
| Q2 | Fate of existing `wiki/ideas/` | **Keep as exploration layer** (literature surveys, concept seedlings); projects move out |
| Q3 | Implementation-record granularity | **Mixed**: `log.md` for ad-hoc entries + `experiments/YYYY-MM-DD-*.md` for milestones |
| Q4 | Projects submodule vs. plain dir | **Separate git submodule** (wiki can go public, projects stay private) |
| Q5 | Remote setup | **Create GitHub remote first, then `git submodule add`** |
| Q6 | Migration scope | **Incremental** — stand up scaffolding + migrate `force-control-policy` now; others on demand |

## 3. Final Architecture

```
awesome-robot-learning/                ← mother repo (personal workspace)
├── .gitmodules                        # two submodules: wiki + projects
├── CLAUDE.md                          # updated nav protocol
├── README.md                          # awesome list (public artefact)
│
├── scripts/                           # pipeline code (unchanged)
├── data/ · logs/ · tests/             # pipeline runtime (unchanged)
│
├── docs/
│   ├── wiki-design.md
│   ├── llm-knowledge-base-design.md   # moved from repo root
│   ├── superpowers/specs/             # brainstorm/design specs (this file)
│   └── proposals/                     # NEW: wiki / system infra proposals
│       └── concept-lint-llm.md        # moved from wiki/ideas/
│
├── wiki/   (submodule, shareable)     ← received knowledge
│   ├── INDEX.md · TOPIC-MAP.md
│   ├── papers/ · concepts/ · codebase/
│   ├── ideas/                         # redefined: cross-paper surveys, concept seedlings
│   └── _queue/
│
└── projects/   (submodule, private)   ← in-progress work
    ├── INDEX.md                       # global project index (status, last update)
    └── <slug>/
        ├── plan.md                    # forward-looking spec
        ├── log.md                     # append-only implementation log
        ├── discussion.md              # archived brainstorm history (optional)
        └── experiments/
            └── YYYY-MM-DD-<name>.md
```

## 4. File Templates

### 4.1 `projects/<slug>/plan.md`

Forward-looking; revised occasionally, versioned via frontmatter `updated`.

```markdown
---
project: <slug>
title: "<one-line description>"
created: YYYY-MM-DD
updated: YYYY-MM-DD
status: planning | active | paused | archived
parent_topic: "<TOPIC-MAP.md path>"
related_papers:
  - "<arxiv_id>"
related_concepts:
  - "<concept-slug>"
tags: []
---

# <Title>

> **TL;DR** — 3 sentences max.

## Motivation
## Hypothesis (falsifiable)
## Prior Art Map (refs into wiki)
## Approach Sketch
## Success / Failure Criteria (incl. MVE)
## Risks
## Next Actions
```

Derived from current `wiki/ideas/TEMPLATE.md` with the Discussion Log section **removed** (it migrates to `log.md`).

### 4.2 `projects/<slug>/log.md`

Append-only. Any granularity. Entries live at the project level; deeper detail links out to `experiments/`.

```markdown
# <Project Name> — Implementation Log

## 2026-05-01 — α-1 baseline smoke test
- Where: `dp_project@abc123` + `projects/force-control-policy/code/eval/`
- Did: ran 50 rollouts on plug_phone_charger, no force, no slow-fast
- Result: 64% success
- See: [[experiments/2026-05-01-alpha1-baseline]]

## 2026-05-02 — decided to drop ACP-style virtual-target encoding
- Reason: ForceVLA2 cross-task data (66% vs 16%) makes heterogeneous output the clear default
- Plan update: removed α-4 variant from ablation grid
```

Guardrails:
- Append only. Do not rewrite or delete historical entries (correct in-place only for typos).
- If `log.md` exceeds ~400 lines, cut a dated archive (`log-2026-Q2.md`) and leave a pointer.

### 4.3 `projects/<slug>/experiments/YYYY-MM-DD-<name>.md`

One file per significant experiment / decision / ablation.

```markdown
---
experiment: alpha1-baseline
date: 2026-05-01
project: force-control-policy
status: complete | running | aborted
---

## Goal
## Setup
- Code: `<external-repo>@<commit>` or `projects/<slug>/code/<path>`
- Data: <dataset + version>
- Hardware: <GPU / platform>
- Config: <key hyperparams or link to config file>

## Metrics (targets)
## Results
## Interpretation
## Next
```

### 4.4 `projects/INDEX.md`

Manually maintained. One row per project.

```markdown
# Projects

| Project | Status | Updated | TL;DR |
|---|---|---|---|
| [[force-control-policy]] | active | 2026-05-01 | Force-aware slow-fast DP at X2Robot platform |
```

## 5. Cross-Reference Rules

- **One-way dependency**: `projects/` → `wiki/` is allowed and encouraged. `wiki/` → `projects/` is **forbidden** (keeps wiki publishable).
- Link syntax inside projects: `[[wiki/concepts/<slug>]]`, `[[wiki/papers/<arxiv_id>]]`, `[[wiki/codebase/<slug>]]`.
- Inside a project, relative links work: `[[experiments/2026-05-01-alpha1-baseline]]`.
- A project may reference `[[../<other-slug>]]` for sister projects, but avoid deep coupling.

## 6. Naming Conventions

- **Slug**: kebab-case describing the *research thrust*, not a phase or version.
  - Good: `force-control-policy`, `external-force-estimation`, `reactive-diffusion-ablation`
  - Bad: `force-vla-phase0`, `rdp-v2`, `may-2026-experiment`
- Phase / version information belongs inside `plan.md`, not in the slug.
- Experiment filenames: `YYYY-MM-DD-<short-kebab-name>.md` (date-first sorts correctly).

## 7. Status Flow

Project-level `status` (in `plan.md` frontmatter):

| Status | Meaning | Entry condition |
|---|---|---|
| `planning` | Plan drafted, not executing yet | Default on creation |
| `active` | `log.md` is accumulating entries | First real work commit |
| `paused` | Deliberate hold | Reason written in last `log.md` entry |
| `archived` | Done (success) or abandoned | Final `log.md` entry states outcome + lessons |

Experiment-level `status` (in experiment frontmatter):
- `running`, `complete`, `aborted`

## 8. Code Location Policy

Default: `projects/<slug>/` is **docs-only** (plan + log + experiments).

Allowed additions:
- `projects/<slug>/code/` — small local scripts (plotting, eval, data analysis). Versioned inside the projects submodule.
- External research code (training, inference, main pipeline) stays in its own repo (e.g. `dp_project`). Referenced from log/experiments as `<repo>@<commit>` URLs.

No enforcement — a single log entry may cite both local files and external commits.

## 9. Migration Plan (incremental)

### Phase A — Scaffolding (do now)

1. Create private GitHub repo `awesome-robot-learning-projects` (via `gh repo create`).
2. `git submodule add` into `projects/`.
3. Commit empty `projects/INDEX.md` + `projects/README.md` describing conventions.
4. Update root `CLAUDE.md` navigation protocol to cover both submodules.

### Phase B — First project migration (do now)

5. Move `wiki/ideas/force-control-policy-plan.md` → `projects/force-control-policy/plan.md`.
6. Strip Discussion Log section from the moved plan (preserve as `projects/force-control-policy/discussion.md`).
7. Create empty `projects/force-control-policy/log.md` + `experiments/` directory.
8. Update plan frontmatter: add `project:`, change `status: active` stays.
9. In wiki, leave a tombstone at `wiki/ideas/force-control-policy-plan.md` (one-liner redirecting to new location) for 1 git commit, then remove in a follow-up commit once no stale links remain.

### Phase C — Cleanup (defer until pressure)

10. `wiki/ideas/external-force-estimation-survey.md` — stays in wiki (it's a survey, not a project). No action.
11. `wiki/ideas/_concept-lint-llm-design.md` + `_concept-lint-2026-04-12.md` → `docs/proposals/concept-lint-llm.md` (merge).
12. Root `log.md` — split: research content into the relevant project log; ops content archived in `docs/ops-log.md` or deleted.
13. Root `llm-knowledge-base-design.md` → `docs/llm-knowledge-base-design.md`.
14. Root debris (`resume_cold_start.log`, `ingest_2505.20829.log`, `resume_cold_start.stdout`) → delete or `logs/archive/`.

### Phase D — Tooling (later, not part of this spec's scope)

- `scripts/project_new.py` — scaffold a new project folder.
- `scripts/project_index.py` — rebuild `projects/INDEX.md` from frontmatter.
- Slash command / Claude workflow for "generate 计划书" and "append log entry".

## 10. Deferred / Open

- **Search across both submodules**: how does the LLM find content spanning wiki + projects? Ripgrep works today; if volume grows, consider embedding both into the existing `data/embeddings/` store.
- **Experiment result attachment**: where do plots, videos, checkpoints live? Proposal: small artefacts in `projects/<slug>/experiments/assets/`; large binaries out-of-band (S3 / LFS) with the experiment file storing only the URL.
- **Access control**: if gary joins collaborators, do they need read-only wiki + project-specific access? Not addressed here.

## 11. Out of Scope

- Changes to the paper discovery / compilation pipeline (`scripts/`).
- Changes to the wiki's internal structure (papers, concepts, codebase, topic-map).
- Cleanup of orphan HTML files in `docs/` (`phase2-redesign.html` etc.) — handle separately.

---

## Approval

Brainstorm session approved the architecture verbally on 2026-04-17. This written spec is for confirmation before invoking `superpowers:writing-plans` to produce the implementation plan.
