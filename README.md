# Kátyúőr (smooth-route)

## Overview
Kátyúőr is an innovative route planning application that considers road quality to help users avoid potholes and poor road conditions.

**Architecture**: Point-based data storage. Routes are only used as tools to collect road points efficiently. All images and data are stored point-based (location + heading), not route-based.

## Documentation

Start here depending on what you need:

- **[AGENTS.md](AGENTS.md)** — entrypoint for developers and AI agents: how to run,
  test, the ML promotion gate, and known pitfalls. Read this first.
- **[docs/MODEL_EXPERIMENTS.md](docs/MODEL_EXPERIMENTS.md)** — the road-quality AI
  story in plain language: what was tried, what shipped, and why.
- **[docs/IMPROVEMENT_PLAN.md](docs/IMPROVEMENT_PLAN.md)** — architecture audit and
  the phased refactor/improvement plan.
- **[docs/PUBLISH_PLAN.md](docs/PUBLISH_PLAN.md)** — publishing plan in two rounds:
  round 1 = read-only public site (Vercel + Neon, R1.1–R1.4); round 2 = user
  submissions (Clerk auth, job queue, quotas; F0–F6).
- **[docs/LAUNCH.md](docs/LAUNCH.md)** — launch kit: name, copy, launch checklist.
- **[docs/SESSION_PROMPTS.md](docs/SESSION_PROMPTS.md)** — copy-paste prompts to
  start a fresh AI session per phase (router-based, low context).
- **[ml/README.md](ml/README.md)** — the RQI model pipeline, its CV results, and the
  ship gate (`ml/evaluate_artifact.py`).
- **[docs/GLOSSARY.md](docs/GLOSSARY.md)** — plain-language glossary of the ML terms
  (QWK, MAE, AUC, 5-fold CV, …) used across these docs.
- **[docs/API_SURFACE.md](docs/API_SURFACE.md)** — GraphQL/REST surface inventory.
- **[frontend/ARCHITECTURE.md](frontend/ARCHITECTURE.md)** — frontend module boundaries.
- **[docs/TrainingGuide.md](docs/TrainingGuide.md)** — how to produce good manual
  labels (applies to the YOLO damage-annotation branch).
- **[DEVELOPMENT.md](DEVELOPMENT.md)** — developer reference: architecture, config,
  CLI, data layout, toolchain.
- `docs/archive/` — superseded strategy notes from before the v2 model (history only).

## The road-quality AI (RQI)

The road quality score shown on the map (RQI 1 = excellent … 4 = poor) comes from
the **v2 model** in `ml/` — a frozen DINOv2-small backbone + SVR head, 5-fold CV
QWK 0.89. It is trained and shipped from the `ml/` pipeline, **not** from the web
UI. YOLO damage detection is a separate concern (it produces the damage polygons
on the detail card, not the RQI). See [docs/MODEL_EXPERIMENTS.md](docs/MODEL_EXPERIMENTS.md).

## Project Structure
- `backend/`: FastAPI + Strawberry GraphQL app (route/point collection, image
  download, DINO RQI + YOLO damage analysis, Clerk auth, Alembic migrations).
  `backend/api/index.py` + `vercel.json` are the read-only Vercel entrypoint;
  `backend/scripts/publish.py` pushes local results to the public read DB.
- `frontend/`: React 19 + Vite 8 + Redux Toolkit/redux-saga map, review and admin
  UI (talks to `/graphql`).
- `ml/`: the RQI model pipeline (feature extraction, experiments, artifact + gate);
  `ml/legacy/` keeps the superseded v1 scripts for reference.
- `scripts/`: DB/data maintenance helpers (`make clear-jobs`, `make purge-data`, …);
  `scripts/legacy/` holds unmaintained one-off diagnostics.
- `docker-compose.yml`: PostGIS database (`db`, on :5433) and an optional backend
  container.

## Public site (round 1)

The public site is **read-only**: analysis runs locally on request, results are
published to a Neon Postgres with `backend/scripts/publish.py`, and two Vercel
projects serve the frontend and the API (`PUBLIC_READ_ONLY=1`, torch-free install
from `backend/requirements.txt`). Point details link to Google Street View instead
of hosting images. Details and the remaining DNS step: [docs/PUBLISH_PLAN.md](docs/PUBLISH_PLAN.md).

## Setup

1.  **Prerequisites**:
    - Docker & Docker Compose (PostGIS)
    - Python 3.11+ (local backend; torch/MPS for the RQI model)
    - Node.js 22+ (frontend; CI runs Node 22)
    - Google Maps API Key (Directions API & Street View Static API enabled)

2.  **Environment Variables**:
    Copy `.env.example` to `.env` in the root directory and fill in at least
    `GOOGLE_MAPS_API_KEY`. For local single-user development without a Clerk
    instance set `AUTH_MODE=disabled` (every request acts as admin — never in
    production).

3.  **Run the application**:

    **Recommended: local dev (venv + Vite)**
    ```bash
    # One-time setup
    python3 -m venv .venv && source .venv/bin/activate
    pip install -e backend/
    (cd frontend && npm ci)

    # PostGIS database (Docker) — serves on :5433
    docker compose up -d db

    # Start backend (:8000) + frontend (:5173) together
    make dev
    ```
    Then open the React app at `http://localhost:5173` (GraphQL at
    `http://localhost:8000/graphql`). A Google Maps API key in the root `.env`
    is required for route → image fetching.

    **Alternative: full Docker**
    ```bash
    docker compose up --build
    ```

    **Tests / gates** (see AGENTS.md; CI runs pytest + typecheck/lint/test):
    ```bash
    cd backend && ../.venv/bin/python -m pytest -q
    cd frontend && npm ci && npm run typecheck && npm run lint && npm test && npm run build
    ```

4.  **CLI Usage**:
    ```bash
    ./cli.sh list-points                                  # list collected points
    ./cli.sh analyze-image data/images/<file>.jpg         # RQI + metadata for one image
    ./cli.sh init-db                                      # create tables (tests/dev only; prod uses Alembic)
    ./cli.sh docker list-points                           # same, inside the backend container
    ```

    **Note**:
    - Available as `smooth-route` after `pip install -e backend/`, or via `./cli.sh`.
    - Route collection, image download and bulk analysis run from the **web UI**
      (job queue + live progress). The CLI commands `collect-points`,
      `download-images`, `fetch-missing-images` and `analyze-points` are currently
      **broken**: they import a removed `processing_service` module.

5.  **Data Storage** (Point-Based):
    - Images are stored **point-based**, NOT route-based
    - Structure: `data/images/{image_id}_{lat}_{lng}_{heading}.jpg`
    - Routes are only used as a tool to collect points efficiently
    - In Docker: automatically mounted and synchronized with host
    - Configurable via `DATA_DIR` environment variable
    - **Important**: No `route_X/` subdirectories - all images directly in `data/images/`

6.  **Access**:
    - **CLI**: `smooth-route --help` or `./cli.sh --help`
    - **Web Interface**: the React app — `cd frontend && npm run dev` → `http://localhost:5173`
      (map with RQI-coloured road quality, route collection, review/admin surfaces)
    - **API**: GraphQL at `http://localhost:8000/graphql` is the product API; the
      remaining REST endpoints (points, health, …) are listed in
      [docs/API_SURFACE.md](docs/API_SURFACE.md). Swagger UI: `http://localhost:8000/docs`.
    - **Health check**: `http://localhost:8000/health`
