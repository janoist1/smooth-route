# AGENTS.md — router for AI agents (and humans)

For any AI coding agent (Claude, GPT, Codex, Cursor, …). **Thin router:** don't read
everything — open only the files in your task's row below. Team roles, branches and
briefs: [docs/TEAM.md](docs/TEAM.md).

## The project in one paragraph

Kátyúőr / smooth-route estimates road quality from Google Street View frames
(RQI 1–4, **1 = excellent, 4 = poor**; 5 is unused) and shows it on a map for route
planning. The **live RQI engine** is the `ml/` v2 model (frozen DINOv2-small + SVR
head + tuned cut-points, in the `ml/cache/rqi_model.joblib` artifact), loaded by the
backend's `dino_service.py` and run on the **raw image**. YOLO (`road_analyzer.py`)
is not a competitor: it draws damage polygons for the detail card, not the RQI. The
public site is read-only (Vercel + Neon); analysis runs locally.

## Router — what to open, what not to

| If you work on… | Open | Don't read |
|---|---|---|
| **RQI model / `ml/`** | [ml/README.md](ml/README.md), [docs/GLOSSARY.md](docs/GLOSSARY.md) | `frontend/**` |
| **Road segments** *(in progress, 2026-11-26 — branches not merged yet)* | backend `road_segments` table, `roadSegments` / `routeQuality` GraphQL, `backend/config/segment_aggregation.json`; ML side `ml/segment_eval.py` + `ml/segment_recipe.json`. Docs land in [docs/API_SURFACE.md](docs/API_SURFACE.md) / [ml/README.md](ml/README.md) with the merge | — |
| **Frontend UI** | [frontend/ARCHITECTURE.md](frontend/ARCHITECTURE.md) | `ml/**` |
| **Backend API / GraphQL** | [docs/API_SURFACE.md](docs/API_SURFACE.md); config, tables, deps: [DEVELOPMENT.md](DEVELOPMENT.md) | `ml/**`, `frontend/**` |
| **Publishing / deploy / auth / queue / quotas** | [docs/PUBLISH_PLAN.md](docs/PUBLISH_PLAN.md) — strategy + your phase only | other phases |
| **Labelling** | [docs/TrainingGuide.md](docs/TrainingGuide.md) | — |
| **"Why is it like this?" / model history** | [docs/MODEL_EXPERIMENTS.md](docs/MODEL_EXPERIMENTS.md) | — |
| **Unclear term** (QWK, MAE, spatial CV…) | [docs/GLOSSARY.md](docs/GLOSSARY.md) | — |
| **Team, briefs, merge/push flow** | [docs/TEAM.md](docs/TEAM.md) | — |
| **Launch copy / name / checklist** | [docs/LAUNCH.md](docs/LAUNCH.md) | — |

Never load `docs/archive/**`, `ml/legacy/`, `scripts/legacy/` — history only.
Principle: **one file = one responsibility, self-contained.** If your row's files
explain the task, open nothing else.

## Environment

- **Python:** always `.venv/bin/python` (torch + MPS live there); never create a new
  venv. In a **git worktree** there is no `.venv` — use the main checkout's
  interpreter by absolute path. Backend tests need neither torch nor a DB.
- **Node** 22+. **DB:** PostGIS in Docker on **:5433** (`docker compose up -d db`).
- **Dev server:** `make dev` (backend :8000 + Vite :5173). Setup: [README.md](README.md#quickstart).
- **Google Maps key:** root `.env` (`GOOGLE_MAPS_API_KEY`), needed for route → image download.

## Gates (run before every merge)

```bash
cd backend && ../.venv/bin/python -m pytest -q              # isolated, no DB/torch
cd frontend && npm ci && npm run typecheck && npm run lint && npm test && npm run build
```

CI (`.github/workflows/ci.yml`) runs pytest and frontend typecheck/lint/test; Vercel
runs the build on push, so run it locally too. **Not green = not done.**

## Critical rules

- **ML promotion gate.** Ship a new/changed `ml/cache/rqi_model.joblib` ONLY if
  `.venv/bin/python ml/evaluate_artifact.py` says **PASS** — spatially grouped 5-fold
  CV (1 km cells, seed=42, nested cut-point tuning), champion thresholds **QWK ≥ 0.774,
  MAE ≤ 0.405, bad-AUC ≥ 0.934**. To replace the champion, the paired ΔQWK 95% CI must
  be above 0. Never cite the old leaky 0.889/0.195/0.970. Details: [ml/README.md](ml/README.md).
- **Raw image.** The model runs on the raw frame; never add preprocessing
  (FastSAM/CLAHE…) to the RQI path — training used raw images too.
- **Canonical data dir:** root `data/` for backend and ML (a relative `DATA_DIR`
  resolves to the repo root). Never recreate `backend/data/`.
- **Commit / push.** Commit on your own branch; **never push** and never touch
  `master` — a push to `master` deploys both Vercel projects and needs the owner's
  approval, as does a Neon publish. Flow: [docs/TEAM.md](docs/TEAM.md).
- **Docs:** adding, moving or retiring a doc → update this router in the same commit.

## Pitfalls

- **One review screen, two panels:** labelling is `/training/:id/review` (score +
  polygons). The web UI never trains the RQI model; `ml/` does.
- **Two backend dependency lists:** `backend/pyproject.toml` (full, with torch) and
  `backend/requirements.txt` (torch-free, Vercel only). A new runtime dependency on the
  read-only path goes into both. **SQLAlchemy `<2.1`** (2.1 maps `postgresql://` to
  psycopg v3). Details: [DEVELOPMENT.md](DEVELOPMENT.md).
- **Most of the CLI is broken** (`collect-points`, `download-images`,
  `fetch-missing-images`, `analyze-points` import a removed module); use the web job flow.
- **Keep the root tidy:** one-off scripts → `scripts/` (if the Makefile uses them) or
  `scripts/legacy/`; superseded notes → `docs/archive/`.

## Status (2026-11-26)

- **Public site:** round 1 (read-only) live on the Vercel default domains, data on
  Neon. Open: **R1.4** (DNS `simaut.hu` / `api.simaut.hu`, key restriction, budget
  alert). Round 2 (auth/queue/quotas) waits for user submissions —
  [docs/PUBLISH_PLAN.md](docs/PUBLISH_PLAN.md).
- **RQI:** honest spatial-CV numbers QWK 0.774 / MAE 0.405 / AUC 0.934; weak in
  Budapest; the v2 champion stays. Next steps: [docs/MODEL_EXPERIMENTS.md](docs/MODEL_EXPERIMENTS.md).
- **In progress** (integration branch `claude/analysis-layer`): road-segment
  aggregation (ML + backend + frontend), high-res road-crop features, VLM attribute
  features, frame-quality audit (`analysis_metadata.frame_quality`), labelling
  queue + mobile quick-rate. Who is on what: [docs/TEAM.md](docs/TEAM.md).
- **Open, no owner:** YOLO retrain + FastSAM decision ([DEVELOPMENT.md](DEVELOPMENT.md)).
