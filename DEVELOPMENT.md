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
- **RQI scale:** one definition in [shared/rqi_scale.json](shared/rqi_scale.json)
  (rules + helpers: [shared/README.md](shared/README.md)); 5 = Kiváló … 1 = Nagyon
  rossz, higher is better (flipped 2026-11-26), the model predicts 2–5. Never
  hard-code levels. The live
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
- `road_segments` — derived ~200 m road pieces with aggregated quality (Alembic
  `0005`, `0007`); rebuilt by `backend/scripts/build_segments.py`. Contract:
  [docs/API_SURFACE.md](docs/API_SURFACE.md).

`street_view_images.analysis_metadata` carries the DINO outputs (`dino_score`,
`dino_p_bad`, `dino_artifact`, `dino_rqi_score_prev`) and the frame-quality flag
(`frame_quality`, written by `ml/frame_quality.py` — [ml/README.md](ml/README.md#frame-quality-flags)).
RQI values are on the canonical scale since Alembic `0006` (2026-11-26).

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
| `GOOGLE_SV_MONTHLY_CAP`, `GOOGLE_SV_JOB_CAP`, `GOOGLE_SV_RATE_PER_S` | `5000`, `1500`, `1` | Street View image budget and pacing — see *Collecting Street View frames safely* (`DAILY_IMAGE_QUOTA` in `config.py` is not enforced anywhere) |
| `DATA_DIR` | `data` | Resolved relative to the **repository root** (never `backend/data/`) |

Runtime-tunable analysis settings live in `backend/config/analysis_settings.json`
and are edited from the Settings page.

### Segment aggregation config

`backend/config/segment_aggregation.json` drives the road-segment layer (code:
`backend/app/services/segment_aggregation.py`; no defaults in code — a missing key
is an error). **Re-run `scripts/build_segments.py` after any change.**

| Key | Meaning |
|---|---|
| `segment_length_m`, `aggregator`, `trim_fraction` | piece length (200 m) and how frame scores combine (`median_score`) |
| `thresholds`, `scale` | cut-points + `{classes, higher_is_worse, bad_class}` on the canonical scale; the ML recipe (`ml/segment_recipe.json`, severity numbering) mirrored. A backend test keeps both equal to [shared/rqi_scale.json](shared/rqi_scale.json); `scripts/sync_rqi_scale.py` converts a new recipe |
| `p_bad_threshold`, `min_images` | good/bad flag from mean P(bad); fewer frames → always "low" |
| `confidence` | `n_ref`, `spread_ref`, `margin_ref` and the `high` / `medium` level cuts |
| `unlabelled_area` | `radius_km` 3, `cap_level` medium: no human label within the radius → confidence capped (reason `unlabelled_area`) |
| `age` | `grace_years` 3, `half_life_years` 5: confidence decay for old imagery |
| `sampling` | collection spacing (`base_spacing_m` 50, `dense_spacing_m` 30, `densify_if`) — see below |

Where the numbers come from: [docs/MODEL_EXPERIMENTS.md](docs/MODEL_EXPERIMENTS.md) (Era 7).

## Collecting Street View frames safely

Street View Static images are billed against a **monthly quota that must never be
exceeded**, and the owner's line may run through a VPN that reacts badly to bursts.
Three rules are enforced in code, not left to discipline:

1. **One counter.** Every image request — route jobs (`services/image_downloader.py`,
   `services/route_collector.py`), `scripts/collect_network.py`,
   `scripts/redownload_images.py`, `ml/recover_missing_images.py` — goes through
   `services/sv_client.py`, which books it in `services/sv_quota.py` *before* sending.
   The counter is `data/quota/street_view.json` (file-locked, shared by all processes
   and worktrees; months follow Google's Pacific-time billing clock). Over the cap
   nothing is sent. Retries are booked too, so the counter can only over-count.
2. **Gentle traffic.** One request at a time, images and (free) metadata together at
   a steady rate, exponential back-off on transient errors. No parallelism.
3. **Stop on trouble.** HTTP 403/429 or an `OVER_QUERY_LIMIT` / `OVER_DAILY_LIMIT` /
   `REQUEST_DENIED` status ends the job at once. What was not fetched stays queued
   or planned, so the same command resumes later. The API key is never written to
   the DB or a log.

| Variable | Default | Meaning |
|---|---|---|
| `GOOGLE_SV_MONTHLY_CAP` | `5000` | Images per calendar month, hard stop (`0` = fetch nothing) |
| `GOOGLE_SV_JOB_CAP` | `1500` | Images per route job / script run (`collect_network.py` has its own `--job-cap`) |
| `GOOGLE_SV_RATE_PER_S` | `1` | Requests per second, images and metadata together |

If images were fetched before the counter existed, set the month's real number once:
`StreetViewQuota.set_used(n)` (the Google Cloud console is the reference).

**Sampling** (`"sampling"` in `backend/config/segment_aggregation.json`, mirrors
`ml/segment_recipe.json`): a first pass takes a frame every `base_spacing_m` (50 m);
after scoring and the segment rebuild, a second pass adds frames every
`dense_spacing_m` (30 m) only on segments whose confidence came out low. Route jobs
do both passes under one per-job budget. Images go where they change the answer.
`densify_if` picks the segments: `["low_confidence"]` (every low-confidence segment,
the recipe's default) or a list of `confidenceReason` values such as
`["few_images", "disagreement"]` — the two reasons more frames can actually fix;
a score that sits on a class boundary (`near_threshold`) does not move with more frames.

**What will it cost?** Dry runs make no Street View request:

```bash
cd backend
../.venv/bin/python scripts/route_cost.py "Budapest, Deák tér" "Szentendre"   # 1 Directions call
../.venv/bin/python scripts/collect_network.py --dry-run                      # no Google call at all
```

**Collect by road network** (no route needed) — `scripts/collect_network.py`: one
cached Overpass request for trunk / primary / secondary roads and their links (no
motorways) in a bbox (default Budapest and surroundings), a point every 50 m on
stretches without frames, ~1 km cells visited round-robin across ~5 km districts so a
limited budget is spread out. Free metadata first (no panorama, a panorama already
stored or not on the planned road, a frame within 5 m → skipped), then the image like
the training frames (600×400, pitch −20, heading = road bearing).

```bash
# 0. backup
docker exec smooth-route-db-1 pg_dump -U postgres -Fc smooth_route > data/backups/pre_collect_$(date +%Y%m%d%H%M).dump
# 1. pass 1 (resumable: run the same command again; Ctrl-C stops cleanly)
../.venv/bin/python scripts/collect_network.py --job-cap 4000 --max-mb 250
# 2. flag unusable frames, score the new ones, rebuild the segments
../.venv/bin/python ../ml/frame_quality.py write --commit --backup <fresh dump>
HF_HUB_OFFLINE=1 ../.venv/bin/python scripts/rescore_dino.py
../.venv/bin/python scripts/build_segments.py
# 3. pass 2 on this job's low-confidence segments, then step 2 again
../.venv/bin/python scripts/collect_network.py --densify --job-cap 1000
# 4. what the job added (images, MB, km, segment classes and confidence)
../.venv/bin/python scripts/collect_network.py --report
```

**After collecting: `make postprocess`** (`backend/scripts/postprocess_new_frames.sh`)
does steps 0 and 2 in one go, incrementally: fresh dump (keeps the last 3), frame
quality, DINO re-score of new frames, `build_segments.py --cached-only`, collector
report, summary. Idempotent and safe while the collector still runs.

Collection also skips user-contributed photospheres (`CAoS…` pano ids); stored ones
are flagged unusable.

Progress is logged per point in `data/collect/<job>.jsonl`. To have the OSM tiles the
rebuild needs in the cache beforehand:
`scripts/build_segments.py --prefetch-bbox minLng,minLat,maxLng,maxLat` (one request at
a time, no DB access). `scripts/rescore_dino.py` only touches frames that do not carry
the current artifact's marker, i.e. the new ones.

## Local development, tests, CI

Setup commands: [README.md](README.md#quickstart); test gates: [AGENTS.md](AGENTS.md).
Other `make` targets: `retrain` ([ml/README.md](ml/README.md#one-command-retrain)),
`postprocess` (above), `backend`, `frontend`, `lint`, `download-models`,
`reimport-images`, `purge-data`, `clean-orphans`, `clear-jobs`, `list-jobs`, `clean`.

`.github/workflows/ci.yml` runs the backend tests on Python 3.12 with a minimal,
**torch-free** dependency set, after `ruff check .` (rules in `backend/pyproject.toml`:
pyflakes `F` + syntax `E9`), and prints coverage (`pytest-cov`). The frontend job runs
typecheck/lint/test and the production build (`npm run build`) on Node 22.
Torch-dependent tests skip themselves there. When a test needs a new package,
add it to the `pip install` line in `ci.yml` too (simulate the CI env locally:
`uv run --no-project --python 3.12 --with pytest --with <each package in ci.yml> python -m pytest`).

**E2E smoke (local only, not in CI yet):** `cd frontend && npm run test:e2e`
(Playwright, `frontend/e2e/`). It checks that the map loads, the grid → road segments
→ frame dots switch on zoom, the segment and point cards, and the route planner
(form, alternatives with Legsimább/Leggyorsabb, route line, route-quality
summary), on a desktop and a phone viewport. The quick-rate smoke
(`e2e/quickrate.e2e.ts`, read-only: it never rates) runs only against an admin
backend (`AUTH_MODE=disabled`, e.g. `API_PROXY_TARGET=http://localhost:8003
E2E_PORT=5181`) and skips itself otherwise. It needs a running backend with map data (`make backend`,
or `API_PROXY_TARGET=http://localhost:8002`), starts its own Vite on :5180
(`E2E_PORT`; or reuse a running app with `E2E_BASE_URL`), and uses the installed
Google Chrome (`E2E_CHANNEL=bundled` after `npx playwright install chromium` to
use Playwright's Chromium). The route test mocks `GetRoute`, so it makes no
Google Directions call and needs no sign-in. The same `API_PROXY_TARGET` also
points `npm run dev` at another backend.

## Static type checking (backend)

`backend/scripts/check_types.py` runs **pyright 1.1.389 in basic mode** on
`backend/app` (`backend/pyrightconfig.json`; tests, scripts and Alembic excluded for
now) and compares the errors per (file, rule) with `backend/pyright_baseline.json`.
CI fails when any bucket grows — **new code must type-check**; never raise the
baseline to make CI pass. After fixing old errors run `check_types.py --update` to
lower it. Heavy packages (torch, numpy, PIL, cv2, …) are stubbed as `Any` in
`backend/typings/`, so the result is identical with or without torch. Locally the
script uses `pyright` from PATH or `npx pyright@1.1.389`.

**TODO — 177 known errors (2026-11-26):** `graphql/queries.py` 53, `services/label_queue_store.py` 33, `services/dino_service.py` 12, `services/training_service.py` 11, `services/road_quality.py` 10, `graphql/mutations.py` 8, `services/image_downloader.py` 8, `services/road_segments.py` 5, others 37. Mostly
SQLAlchemy `Column[...]` values passed where plain types are expected (legacy 1.x
style models) and `Optional` members used after a lazy load.

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
