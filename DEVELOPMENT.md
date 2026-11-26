# Smooth Route (Kátyúőr) — Development Reference

Developer reference (updated 2026-11-26): architecture, config, dependencies, CLI,
data layout. How to run/test and the hard rules: [AGENTS.md](AGENTS.md). Topic docs
linked below are the source of truth for their area.

## Core ideas

- **Point-based data.** A road point is a location + heading (`street_view_images`
  row). Routes are only a tool to collect points (A→B path); they are never stored.
- **Deduplication.** Before creating a point, an existing one within
  `DEDUPLICATION_RADIUS_METERS` (default 10 m) and `DEDUPLICATION_HEADING_TOLERANCE`
  (default 30°) is reused, so overlapping routes don't re-download images.
- **RQI 1–4, lower is better** (1 = excellent, 4 = poor; 5 is not used). The live
  score comes from the **v2 model** in `ml/` (frozen DINOv2-small + SVR head,
  artifact `ml/cache/rqi_model.joblib`), loaded by `backend/app/services/dino_service.py`
  and run on the **raw** image. YOLO (`road_analyzer.py`) only produces damage
  polygons for the detail card. Background: [docs/MODEL_EXPERIMENTS.md](docs/MODEL_EXPERIMENTS.md).

## Architecture

| Layer | Stack | Where |
|---|---|---|
| Backend | FastAPI + Strawberry GraphQL, SQLAlchemy 2.0 + GeoAlchemy2, Alembic, Typer CLI | `backend/app/` |
| Database | PostgreSQL 16 + PostGIS 3.4 (Docker, host port **5433**) | `docker-compose.yml` |
| Auth | Clerk JWT (`AUTH_MODE=clerk`) or single-user local mode (`AUTH_MODE=disabled`) | `backend/app/core/auth.py`, `graphql/permissions.py` |
| Frontend | React 19, Vite 8, Redux Toolkit + redux-saga (saga-toolkit), Apollo Client 4, react-leaflet, Clerk | `frontend/src/` |
| ML | DINOv2 + SVR pipeline, spatial-CV ship gate | `ml/` |
| Public deploy (round 1) | Two Vercel projects (frontend + read-only API) + Neon Postgres | `backend/api/`, `backend/vercel.json`, `frontend/vercel.json` |

- API inventory: [docs/API_SURFACE.md](docs/API_SURFACE.md) (GraphQL is the product API).
- Frontend module boundaries: [frontend/ARCHITECTURE.md](frontend/ARCHITECTURE.md).
- Publishing rounds and phases: [docs/PUBLISH_PLAN.md](docs/PUBLISH_PLAN.md).

### Database tables (`backend/app/models/models.py`)

- `street_view_images` — the road points: lat/lng/heading/pitch, PostGIS `location`,
  `pano_id`, `capture_date` (Street View capture month), `image_url`, `rqi_score`,
  `dino_rqi_score`, damage counts/types, `analysis_metadata`.
- `training_data` — manual labels (`manual_rqi`, annotations, tags) keyed by image file.
- `jobs` — background job state (progress, message, result) shown live in the UI.
- `users` — Clerk-linked users with a `user`/`admin` role.

Schema changes go through **Alembic** (`backend/alembic/versions/`); the app
migrates on startup unless `RUN_MIGRATIONS_ON_STARTUP=false`. `init-db` /
`create_all` is for tests and throwaway DBs only.

## Configuration

Settings live in `backend/app/core/config.py` (pydantic-settings) and are read from
the root `.env` — copy `.env.example`. The important ones:

| Variable | Default | Notes |
|---|---|---|
| `GOOGLE_MAPS_API_KEY` | — | Directions + Street View Static; needed for route → image download |
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5433/smooth_route` | psycopg2 driver (keep SQLAlchemy `<2.1`, see below) |
| `AUTH_MODE` | `clerk` | `disabled` = everyone is admin; local development only |
| `CLERK_SECRET_KEY`, `CLERK_ISSUER`, `CLERK_AUTHORIZED_PARTIES` | — | Clerk instance; frontend needs `VITE_CLERK_PUBLISHABLE_KEY` in `frontend/.env` |
| `RUN_MIGRATIONS_ON_STARTUP` | `true` | `false` on Vercel (Neon schema is managed by `publish.py`) |
| `PUBLIC_READ_ONLY` | `false` | `1` on the public API: query schema only, no mutations, no local-only routes |
| `ALLOWED_ORIGINS` | `https://simaut.hu` | CORS origins in read-only mode |
| `DAILY_IMAGE_QUOTA` | `1000` | Street View download cap |
| `DATA_DIR` | `data` | Resolved relative to the **repository root** (never `backend/data/`) |

Runtime-tunable analysis settings live in `backend/config/analysis_settings.json`
and are edited from the Settings page.

## Local development, tests, CI

Setup commands: [README.md](README.md#quickstart); test gates: [AGENTS.md](AGENTS.md).
Other `make` targets: `backend`, `frontend`, `lint`, `download-models`,
`reimport-images`, `purge-data`, `clean-orphans`, `clear-jobs`, `list-jobs`, `clean`.

`.github/workflows/ci.yml` runs the backend tests on Python 3.12 with a minimal,
**torch-free** dependency set (plus `ruff --select F821`), and the frontend
typecheck/lint/test on Node 22. Torch-dependent tests skip themselves there. The
production build (`npm run build`) is not in CI — Vercel runs it on push.

**E2E smoke (local only, not in CI yet):** `cd frontend && npm run test:e2e`
(Playwright, `frontend/e2e/`). It checks that the map loads, the grid → points
switch on zoom, the point detail card and the route-planner form, on a desktop
and a phone viewport. It needs a running backend with map data (`make backend`,
or `API_PROXY_TARGET=http://localhost:8002`), starts its own Vite on :5180
(`E2E_PORT`; or reuse a running app with `E2E_BASE_URL`), and uses the installed
Google Chrome (`E2E_CHANNEL=bundled` after `npx playwright install chromium` to
use Playwright's Chromium). The route test mocks `GetRoute`, so it makes no
Google Directions call and needs no sign-in. The same `API_PROXY_TARGET` also
points `npm run dev` at another backend.

## Dependencies — two backend sets

- `backend/pyproject.toml` — full local/dev install (ultralytics → torch, OpenCV, …).
- `backend/requirements.txt` — **deploy-only**, torch-free set for the Vercel
  function. `backend/.vercelignore` hides `pyproject.toml` from Vercel so its Python
  builder falls back to this file; keep it torch-free (serverless size cap).
- SQLAlchemy is capped `<2.1` in both files and in CI: 2.1 maps plain
  `postgresql://` URLs to psycopg v3 instead of psycopg2. Lift the cap only together
  with a driver switch.
- Security floors for transitive packages (`starlette`, `urllib3`) are pinned in
  both files; refresh them with `pip-audit`.

Frontend: the lockfile was last resolved with npm 11 (npm 10.9 crashes resolving
Vitest 4's peer set); `npm ci` works with npm 10.

## CLI

`smooth-route` (after `pip install -e backend/`) or `./cli.sh [docker] <command>`:

| Command | Status |
|---|---|
| `init-db` | works — `create_all`, tests/dev only |
| `list-points` | works |
| `analyze-image <path>` | works — prints RQI + metadata for one image |
| `collect-points`, `download-images`, `fetch-missing-images`, `analyze-points` | **broken** — import the removed `app.services.processing_service`; use the web UI (job queue) instead |

## Data layout

```
data/                       # repo root; DATA_DIR; mounted at /app/data in Docker
├── images/                 # {image_id}_{lat}_{lng}_{heading}.jpg — flat, no route folders
└── static/previews/        # generated previews (not mounted in read-only mode)
ml/labels.csv               # exported labels (ml/export_labels.sh)
ml/cache/rqi_model.joblib   # the shipped RQI artifact (tracked); other caches are regenerable
```

`data/` is git-ignored. The public site stores no images: point details deep-link
to Google Street View (`pano_id` or viewpoint).

## RQI model workflow

Train and ship only through the `ml/` pipeline; a new `ml/cache/rqi_model.joblib`
ships only if `ml/evaluate_artifact.py` prints **PASS** (thresholds and protocol:
[ml/README.md](ml/README.md)). `ml/legacy/` is reference only; the web UI does not
train the RQI model. Labelling happens on `/training/:id/review`
([docs/TrainingGuide.md](docs/TrainingGuide.md)).

There is deliberately **no web model selector**: DINO (RQI, "how bad?") and YOLO
(damage polygons, "what is wrong?") answer different questions. The
`rqi_display_source` setting only picks which score the map shows.

YOLO: one loader (`backend/app/services/yolo_loader.py`) serves both the review
annotator (`inference.py`) and route analysis (`road_analyzer.py`). FastSAM
(`preprocessing.py`) survives only as a quarantined review diagnostic
(`performReviewAction("preview_preprocessing")`), never on the RQI path. **Open:**
retrain YOLO on the new annotations, then decide whether FastSAM can go.

## Repository map

```
backend/          FastAPI app, Alembic, tests, Vercel entrypoint (api/), publish script (scripts/)
frontend/         React app (src/modules/* = feature modules with slice/sagas/hooks)
ml/               RQI pipeline; ml/legacy/ = superseded v1 scripts
scripts/          maintenance helpers used by the Makefile; scripts/legacy/ = old one-offs
docs/             plans, API surface, glossary, experiments; docs/archive/ = superseded notes
AGENTS.md         router for developers and AI agents
```

## Git

`master` is deployed: both Vercel projects auto-deploy on push. Branch/merge/push
policy: [docs/TEAM.md](docs/TEAM.md).
