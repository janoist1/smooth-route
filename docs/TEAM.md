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
address of their own: reach them only through the lead. Statuses as of 2026-11-26
evening; the live state is the ticket board (`python3 tools/board.py list`).

| Role | Who | Scope | Status | How to reach |
|---|---|---|---|---|
| Lead | session `local_41d0e121-313f-44cd-aa60-914d84df2820` "Útvonalak minőségi jelölése térképen" | coordinates, writes briefs, merges into `claude/analysis-layer`, talks to the owner | active | owner directly; agents: `SendMessage` |
| QA | session `local_1abdbc43-3382-4c7e-8c1b-a17dc66c9648` (`qa`) "QA: integrációs ág ellenőrzése" | runtime smoke tests + review of the integration branch; Playwright E2E | active (T-46 pre-release regression) | `SendMessage` |
| ML high-res features | session `local_d7ff59b2-1888-4337-a822-3cd0f9770565` (`ml-hires`) "ML: high-res road-crop features" | high-res / YOLO features (T-14), geographic reliability (T-41), unlabelled-area cap (T-44) | done | `SendMessage` |
| Labelling queue | session `local_a23ad50a-216c-412f-a858-146cfad23089` (`label-queue`) "Labelling: active-learning queue + mobile quick-rate" | label queue + quick-rate (T-13), re-check mode (T-35), route alternatives (T-23), photosphere skip (T-42) | done | `SendMessage` |
| Frame quality | session `local_03836c8c-9acc-4c99-aacf-13f6d4bfce53` (`frame-quality`) "Data: frame quality audit" | frame-quality flags (T-12), novelty check (T-33), `make retrain` (T-37), incremental post-processing (T-38) | active (T-38) | `SendMessage` |
| VLM attributes | session `local_cceb44fa-3d54-4217-86df-83d46d2458f1` (`ml-vlm-attrs`) "ML: VLM image-analysis features" | VLM attributes as features + distillation + label audit (T-15) | done | `SendMessage` |
| RQI scale | session `local_233868f2-f73d-4ce7-96c7-f91cc96a4bf1` (`rqi-scale`) "RQI scale: one canonical 1–5 scale everywhere" | canonical 5-level scale + flip to 5 = Kiváló, dev DB migrated (T-11); docs final pass (T-26) | active (T-26) | `SendMessage` |
| Security review | session `local_ff4aa73d-c156-4010-82d4-8ae7499fe822` (`security-review`) "Security & cost review: public read-only API" | public API limits, secrets, dependency audit (T-16, T-29), release runbook (T-39) | active (T-45 pre-release delta) | `SendMessage` |
| ML segment aggregation | lead's subagent, Fable 5.2 | `ml/segment_eval.py`, `ml/segment_recipe.json` (T-9) | done | – |
| Backend road segments | lead's subagent, Fable 5.2 | `road_segments`, `roadSegments`/`routeQuality` (T-7), re-score (T-8), Budapest collection (T-34) | T-34 in review | via lead |
| Frontend segment layer | lead's subagent, Fable 5.2 | map segment layer, segment + route cards (T-5) | done | – |
| Cloud sessions | `cloud-ci`, `cloud-perf`, `cloud-docs` | CI hardening (T-18), bundle size (T-19); docs (T-17) never delivered → T-26 | T-18/T-19 doing | via lead |
| Frontend type debt | lead's subagent, Sonnet | `tsc` errors | done, merged | – |
| Pilot labellers ×4 | lead's subagents, 2× Fable 5.2, 2× Opus 5.5 | AI-labelling pilot | done | – |
| Codex | `codex exec` runs started by the lead (skill `codex`, owner's ChatGPT quota) | well-scoped tickets, independent reviews | available (from 2026-11-26) | via lead |

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
- **Codex** (OpenAI, the owner's ChatGPT subscription, user skill `codex`): the owner
  has a large Codex quota that otherwise goes unused, so give Codex well-scoped tickets
  and independent reviews. Implementation runs in its own worktree with
  `codex exec -s workspace-write`; Codex does not commit — the lead reads the diff, runs
  the gates and commits. Reviews: `codex exec review --base claude/analysis-layer`.
  Codex reads [AGENTS.md](../AGENTS.md) itself; the brief must still be complete.
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

## Ticket board

One board for the whole team: `tools/board.py` (no deps, no server). Data and the
rendered page live in the **main checkout** (`board/tickets.json`, `board/index.html`,
gitignored), so every worktree and session sees the same board; the owner just opens
`board/index.html` (auto-refreshes every minute).

- Columns: `todo` → `doing` → `review` (ready to merge / in QA) → `done`; `owner` =
  waiting on the owner's decision or action.
- Every agent: `python3 tools/board.py move T-<n> doing` when starting, `note` for a
  one-line progress update, `move … review` when its branch is ready, `add` for new
  work it discovers. The lead moves tickets to `done` after merging.
- Titles short, notes one line, English.
- **Who and how much:** `board.py work T-<n> --who … --model … --effort … --codex-session <id>`
  (exact tokens from the Codex rollout) or `--claude-transcript <path> --since … --until …`
  (estimate by time window). The card shows who/effort/tokens; a click opens the details.
- **Owner decisions:** every `owner` ticket carries `board.py ask` (question, 2–4 options,
  recommendation, one-line why, in Hungarian). When the owner says "menjünk végig", the
  lead walks through them one by one with a question panel (AskUserQuestion), records the
  answer with `decide` and moves the ticket on.
- **Always current** (owner's request): the lead creates the ticket *before* starting a
  session, subagent or Codex run, moves it the moment work is merged or dropped, and
  every agent posts a `note` at each milestone. The board must never lag the work.
- Record **major decisions** on the ticket with `decide T-<n> "…"`: what was chosen
  and why, in plain words a non-specialist owner can follow (no jargon without a
  short explanation).

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
- **Pilot before scale-up.** Decisions from 2026-11-26 (numbers and reasons:
  [MODEL_EXPERIMENTS.md](MODEL_EXPERIMENTS.md)):
  - AI labelling pilot: VLM labellers QWK 0.63 / 0.72 vs the model's 0.84 → no VLM
    labelling at scale.
  - High-res road features: refuted; one gated two-view candidate (+0.021 QWK, 11×
    cost) → not promoted until a holdout region exists.
  - VLM attributes as features: first measurably better challenger (+0.031 QWK) but
    needs a VLM call per frame → not promoted.
  - Novelty and geographic distance: do not predict error → not used; a fixed 3 km
    "unlabelled area" confidence cap instead.
  - Scale: one 5-level scale, 5 = Kiváló (owner); flip is lossless (gate unchanged).
- Record such decisions on the ticket (`board.py decide`).

## Doc rules

- To the point: no irrelevant, duplicated or junk content.
- One doc = one responsibility, self-contained. A fact lives in **one** place;
  other docs link to it.
- [AGENTS.md](../AGENTS.md) is the router: when you add, move or retire a doc,
  update the router row in the same commit.
- Finished plans and superseded notes go to `docs/archive/` — history only, never
  loaded by agents.
- English; status lines carry a date.
