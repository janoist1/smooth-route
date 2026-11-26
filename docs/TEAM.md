# AI team and way of working

How the AI team is organised, so it keeps working when sessions come and go. Every
session and agent reads this when it starts team work. Update the roster whenever a
member starts or finishes.

## People and language

- **Owner** (human): decides product questions, approves every push to `master` and
  every Neon publish. Follows visible sessions from the phone (Remote Control).
- **Lead** (main session): the only one who talks to the owner (in Hungarian).
- Everything else — docs, code comments, commits, briefs, reports — is **English**.
  Product UI text stays Hungarian.

## Roster

Sessions are reached with `SendMessage` to the session id. Subagents have no
address of their own: reach them only through the lead.

| Role | Who | Scope | Status | How to reach |
|---|---|---|---|---|
| Lead | session `local_41d0e121-313f-44cd-aa60-914d84df2820` "Útvonalak minőségi jelölése térképen" | coordinates, writes briefs, merges into `claude/analysis-layer`, talks to the owner | active | owner directly; agents: `SendMessage` |
| QA | session `local_1abdbc43-3382-4c7e-8c1b-a17dc66c9648` (`qa`) "QA: integrációs ág ellenőrzése" | runtime smoke tests + review of the integration branch | active | `SendMessage` |
| ML high-res features | session `local_d7ff59b2-1888-4337-a822-3cd0f9770565` (`ml-hires`) "ML: high-res road-crop features" | higher-resolution road-region DINOv2 features + YOLO damage features, under the spatial gate | active | `SendMessage` |
| Labelling queue | session `local_a23ad50a-216c-412f-a858-146cfad23089` (`label-queue`) "Labelling: active-learning queue + mobile quick-rate" | smart unlabelled-frame queue + mobile quick-rate page for the owner | active | `SendMessage` |
| Frame quality | session `local_03836c8c-9acc-4c99-aacf-13f6d4bfce53` (`frame-quality`) "Data: frame quality audit" | flags unusable frames (non-road, dark, blurred, duplicates) in `analysis_metadata.frame_quality` so segments skip them | active | `SendMessage` |
| VLM attributes | session `local_cceb44fa-3d54-4217-86df-83d46d2458f1` (`ml-vlm-attrs`) "ML: VLM image-analysis features" | Fable subagents describe each labelled frame with a fixed attribute schema; tested as model features (+ distillation) under the spatial gate; also a label-audit list | active | `SendMessage` |
| RQI scale | session `local_233868f2-f73d-4ce7-96c7-f91cc96a4bf1` (`rqi-scale`) "RQI scale: one canonical 1–5 scale everywhere" | single source of truth for the 5-level scale (`shared/rqi_scale.json`), phase 2 = numeric direction flip if the owner decides so | active | `SendMessage` |
| Security review | session `local_ff4aa73d-c156-4010-82d4-8ae7499fe822` (`security-review`) "Security & cost review: public read-only API" | GraphQL limits, input caps, secrets scan, dependency audit, owner dashboard checklist | active | `SendMessage` |
| ML segment aggregation | lead's subagent, Fable 5.2 | `ml/segment_eval.py`, `ml/segment_recipe.json` | in progress | via lead |
| Backend road segments | lead's subagent, Fable 5.2 | `road_segments`, `roadSegments`/`routeQuality` GraphQL | in progress | via lead |
| Frontend segment layer | lead's subagent, Fable 5.2 | map segment layer | in progress | via lead |
| Docs | lead's subagent, Opus 5.5 | all `*.md`, router, this file | in progress | via lead |
| Frontend type debt | lead's subagent, Sonnet | `tsc` errors | done, merged | – |
| Pilot labellers ×4 | lead's subagents, 2× Fable 5.2, 2× Opus 5.5 | AI-labelling pilot | done | – |

## Roles

- **Lead** — splits work, writes briefs, merges, runs the gates on the integration
  branch, keeps this roster and the router's status block current.
- **Specialists** — ML (`ml/`, the promotion gate), backend (API, DB, Alembic),
  frontend (`frontend/`), labelling (label tooling and queues), docs (all `*.md`),
  QA/review (independent check of the integration branch: gates, smoke test, diff
  review; reports, does not fix unless asked).

## Starting members, choosing models

- An ongoing role gets a **visible session** (the owner can follow it); record its
  session id in the roster when it starts. Background subagents are only for short
  one-off pieces.
- **Premium model** (Opus 5.5, Fable 5.2) for design-heavy work: new features, ML
  experiments, architecture, reviews. **Cheaper model** (Sonnet) for mechanical work:
  type fixes, renames, dependency bumps, translations of settled text.
- **Usual pattern:** sessions run on Opus and delegate heavy image reading and
  implementation to Fable subagents (Fable has its own weekly usage bucket).
- When the model choice itself is the question, run a small comparison pilot first
  (the labelling pilot compared four labellers on two models).
- **Bandwidth:** every image an agent views stays in its context and is re-uploaded
  with each later request. Keep image-reading agents small (≤ 20 images per agent,
  ≤ 2 in parallel) when the owner's connection is limited; no large downloads or
  uploads (model weights, datasets, remote GPU) without checking the connection.

## How work flows

1. The lead creates the brief. The agent gets its **own git worktree branched from
   the integration branch** (`claude/analysis-layer`).
2. Small, self-explanatory commits on that branch. Never push, never touch `master`
   or other worktrees, no bare `git stash` (the stash is shared between worktrees).
3. Gates green on the branch ([AGENTS.md](../AGENTS.md)) → the lead merges into the
   integration branch → QA checks the integration branch.
4. The owner approves the push to `master`, because **a push to `master` deploys**
   both Vercel projects. Publishing data to Neon (`backend/scripts/publish.py`) is a
   separate owner-approved step.

## Briefs

A brief is the agent's whole context, so it contains:

- **Goal** and why, in a few lines.
- **Read:** the router row(s) to open; **don't touch:** files other agents own.
- **Done when:** concrete criteria + the gates to run.
- **Report:** branch, commits, results with numbers, follow-ups.

The agent does not ask questions mid-task: it decides, documents the decision in the
report, and moves on. Template:

```
Repo: /Users/i/Dev/smooth-route — read AGENTS.md, open only the row for this task.
Goal: <what and why>
Branch: own worktree from claude/analysis-layer; commit, never push.
Don't touch: <files owned by others>
Done when: <criteria>; gates green (AGENTS.md).
Report: branch, commits, results (numbers), follow-ups.
```

## Check-ins

- Sessions report to the lead at each milestone (commit SHA + gate status) and as
  soon as they are blocked. Subagents report once, at the end.
- The lead checks quiet sessions and keeps the roster's status column current.

## Short-lived workflows

One task per session/agent; its context is thrown away afterwards. Results live in
**commits and docs, not in chat**: anything the next agent needs (a decision, a
number, a gotcha) goes into the owning doc before the task ends. A new session
starts from [AGENTS.md](../AGENTS.md), not from earlier conversations.

## How we decide

- Every model or labelling change is measured against the **honest baseline** —
  the spatial-CV gate in [ml/README.md](../ml/README.md) — never against the old
  leaky numbers.
- **Pilot before scale-up.** AI-labelling pilot (2026-11): vision-LLM labellers agreed
  with the expert at QWK 0.63 / 0.72, worse than the model itself (0.84) → dropped.
  Tooling (reproducible scripts + prompt template) is in `data/vlm/` (git-ignored).

## Doc rules

- To the point: no irrelevant, duplicated or junk content.
- One doc = one responsibility, self-contained. A fact lives in **one** place;
  other docs link to it.
- [AGENTS.md](../AGENTS.md) is the router: when you add, move or retire a doc,
  update the router row in the same commit.
- Finished plans and superseded notes go to `docs/archive/` — history only, never
  loaded by agents.
- English; status lines carry a date.
