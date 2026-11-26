# Kátyúőr (smooth-route)

A road-quality map for route planning. Google Street View frames are scored by a
vision model (RQI 1 = excellent … 4 = poor) and shown on a map, so you can see —
and avoid — bad roads. Data is **point-based** (location + heading); routes are
only a tool to collect points.

- **RQI model:** frozen DINOv2-small + SVR head, trained and shipped from `ml/`
  (not from the web UI). Honest numbers and the ship gate: [ml/README.md](ml/README.md).
  YOLO damage detection is separate: it draws damage polygons on the detail card.
- **Public site (round 1):** read-only — analysis runs locally, results are
  published to Neon and served by two Vercel projects; point details deep-link to
  Street View. Plan and status: [docs/PUBLISH_PLAN.md](docs/PUBLISH_PLAN.md).

## Documentation

- **[AGENTS.md](AGENTS.md)** — the router: which doc to open for which task, how
  to run and test, the hard rules. Start here (humans too).
- **[docs/TEAM.md](docs/TEAM.md)** — how the AI team works (roles, branches,
  briefs, doc rules).
- **[DEVELOPMENT.md](DEVELOPMENT.md)** — developer reference: architecture,
  config, dependencies, CLI, data layout.

## Quickstart

Prerequisites: Docker, Python 3.11+, Node 22+, a Google Maps API key
(Directions + Street View Static).

```bash
cp .env.example .env          # set GOOGLE_MAPS_API_KEY; AUTH_MODE=disabled for local single-user dev
make setup                    # .venv + backend (editable) + frontend deps
docker compose up -d db       # PostGIS on :5433
make dev                      # backend :8000 (GraphQL /graphql) + frontend :5173
```

Tests and gates: see [AGENTS.md](AGENTS.md).
