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
- **[docs/PUBLISH_PLAN.md](docs/PUBLISH_PLAN.md)** — publishing plan: auth (Clerk),
  persistent job queue, download quotas/dedup, and the Hetzner+Cloudflare deploy
  target, phased F0–F6.
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

## The road-quality AI (RQI)

The road quality score shown on the map (RQI 1 = excellent … 4 = poor) comes from
the **v2 model** in `ml/` — a frozen DINOv2-small backbone + SVR head, 5-fold CV
QWK 0.89. It is trained and shipped from the `ml/` pipeline, **not** from the web
UI. YOLO damage detection is a separate concern (it produces the damage polygons
on the detail card, not the RQI). See [docs/MODEL_EXPERIMENTS.md](docs/MODEL_EXPERIMENTS.md).

## Project Structure
- `backend/`: FastAPI + Strawberry GraphQL app (route/point collection, image
  download, YOLO + DINO analysis).
- `frontend/`: Vite/React map & training UI (talks to `/graphql`).
- `ml/`: the RQI model pipeline (feature extraction, experiments, artifact + gate).
- `docker-compose.yml`: Orchestrates the backend and PostGIS database.

## Setup

1.  **Prerequisites**:
    - Docker & Docker Compose
    - Google Maps API Key (Directions API & Street View Static API enabled)

2.  **Environment Variables**:
    Create a `.env` file in the root directory:
    ```bash
    GOOGLE_MAPS_API_KEY=your_api_key_here
    ```

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

    **Tests / gates** (see AGENTS.md):
    ```bash
    cd backend && ../.venv/bin/python -m pytest -q
    cd frontend && npm run typecheck && npm run lint && npm test
    ```

4.  **CLI Usage** (Point-Based):
    ```bash
    # Collect points along a route (route is only a tool!)
    ./cli.sh collect-points "47.514700,19.040230" "47.513513,19.047038"
    
    # List all collected points
    ./cli.sh list-points
    
    # Download images for all points that have URLs but no local files yet
    ./cli.sh download-images
    
    # Limit number of downloads
    ./cli.sh download-images --limit 100
    
    # Analyze points
    ./cli.sh analyze-points --simple --save
    
    # Or using Docker
    ./cli.sh docker collect-points "Start" "End"
    ./cli.sh docker list-points
    ./cli.sh docker download-images
    
    # After installing: smooth-route command is available
    smooth-route --help
    ```
    
    **Note**: 
    - The CLI is available as `smooth-route` command after installation, or via `./cli.sh` wrapper script.
    - **Point-based architecture**: Routes are only tools to collect points. No routes are stored!

5.  **Data Storage** (Point-Based):
    - Images are stored **point-based**, NOT route-based
    - Structure: `data/images/{image_id}_{lat}_{lng}_{heading}.jpg`
    - Routes are only used as a tool to collect points efficiently
    - In Docker: automatically mounted and synchronized with host
    - Configurable via `DATA_DIR` environment variable
    - **Important**: No `route_X/` subdirectories - all images directly in `data/images/`

6.  **Access**:
    - **CLI**: `smooth-route --help` or `./cli.sh --help`
    - **Web Interfaces**:
      - **Map Visualization**: `http://localhost:8000/map.html`
        - Visualizes road points on Google Maps
        - Color-coded road segments by RQI (green/yellow/orange/red)
        - Shows statistics and legend
      - **Route Collection**: Kattints a jobb alsó sarokban lévő ➕ gombra a térképen
        - Click two points on the map to select origin and destination
        - Start processing: collect points → download images → analyze
        - Real-time progress tracking with step indicators
        - Error handling and status messages
    - **API**:
      - API Docs: `http://localhost:8000/docs` (Swagger UI)
      - Points API: `http://localhost:8000/api/v1/points`
      - Process Route: `POST /api/v1/process-route`
      - Job Status: `GET /api/v1/job/{job_id}`
      - Config API: `http://localhost:8000/api/v1/config`
    - **Health check**: `http://localhost:8000/health`
