# Public API: security and cost limits

*Status 2026-11-27 (T-105 independent public API review).*

The round-1 API (`PUBLIC_READ_ONLY=1`, Vercel → Neon) is anonymous. Anything a
stranger can call costs money or capacity: Google Directions/Geocoding
(`getRoute`), Neon compute and egress, Vercel function time and bandwidth. The
code caps every **single request** and applies a best-effort daily Google budget;
per-IP rates and hard money caps live in
the dashboards (owner checklist below). Nothing here knows who is calling.

## What the public deploy serves

| Surface | Public deploy | Local dev |
|---|---|---|
| `POST /graphql` (read schema) | yes | full schema (reads + mutations) |
| `GET /graphql` (queries via GET, GraphiQL) | no | yes |
| `/health`, `/` | yes | yes |
| REST job stream `/api/v1/job/{id}/stream` (the only REST route left, T-65), `/images/*`, `/api/v1/exports/*`, `/previews` | **not mounted** | yes |
| `/docs`, `/redoc`, `/openapi.json` | no | yes |
| Introspection (`__schema`, `__type`; `__typename` is fine) | no | yes (codegen) |
| Unexpected exception text in errors | masked (`Unexpected error.`, logged server-side) | shown |
| `job` / `activeJob` | `PublicJob`: state, progress, generic message and timestamps; no stored diagnostics | full `Job`, including message/error/result |
| CORS | `ALLOWED_ORIGINS`, no credentials, GET/POST/OPTIONS | any `localhost`/`127.0.0.1` port |

Wiring: `backend/app/main.py`; security headers on every response:
`backend/app/core/security_headers.py`; frontend headers: `frontend/vercel.json`.

## Request limits (`backend/app/graphql/limits.py`)

Registered in `schema.py` via `schema_extensions(public=...)`. Rejections happen
**before execution** (no DB row read, no Google call) and carry
`extensions.code = "BAD_USER_INPUT"`.

| Limit | Value | Why |
|---|---|---|
| Tokens per document | 2 000 | frontend max ~150; Strawberry's own `MaxTokensLimiter` is a no-op on the async (HTTP) path in 0.287, so `MaxTokensParser` replaces it |
| Expanded selections per document | 10 000 | iterative, cycle-safe, memoized per selection set/fragment; checked before depth/aliases and GraphQL validation; repeated spreads count toward the budget |
| Query depth | 8 | frontend max 3 (introspection not counted) |
| Aliases | 10 | frontend uses none |
| `getRoute` + `routeAlternatives` per request | 1 in total | public: at most 1 Directions call, no Geocoding or retries; `alternatives=true` is billed as one call |
| Directions + Geocoding per Pacific day | `GOOGLE_DIRECTIONS_DAILY_CAP=300` combined attempts (0 blocks all) | reserve before every call, including failed attempts; local and public modes |
| `routeAlternatives` route quality | only for Google routes ≤ 800 km and ≤ 20 000 points; longer ones come back unmeasured (coverage 0) | Google picks the route: a text destination abroad could mean 3 × 2 000 km of matching |
| `Point.segmentId` | only below `point(id)`; refused under `points` / `segmentFrames` | one PostGIS query per point (~5 ms locally, a Neon round trip in prod): `points(limit: 20000) { segmentId }` = 20 000 queries |
| `segmentFrames` per request | 2 | ~10–35 ms each |
| `getRoute` / `routeAlternatives` origin/destination | ≤ 200 chars, no control chars; decimal `lat,lng` must be inside `SERVICE_AREA` (HU + margin); other numeric formats and `name:value` location modifiers are rejected | no `heading=…:`, `side_of_road:`, `via:` or `place_id:` address fallback |
| `points` | `limit` ≤ 20 000 with bbox (= frontend `MAP_POINT_LIMIT`), ≤ 1 000 without; `offset` ≤ 100 000; bbox exactly 4 numbers, ≤ 1 deg² | a 3-element bbox used to be ignored → whole table |
| `roadQualityGrid`, `roadSegments` | zoom 0–22; bbox no larger than an 8K screen at that zoom (×2); no bbox only up to zoom ~5 | stops "street zoom over the whole country" |
| `routeQuality(path)` per request | 1 | |
| `routeQuality(path)` | ≤ 20 000 points (= `segment_read.MAX_PATH_POINTS`), ≤ 800 km total; antimeridian-crossing edges rejected | matcher costs ~1.1 ms CPU per km (benchmarked) |
| Path allocations (independent service guards) | ≤ 25 000 interpolated points, 4 096 envelopes, 250 000 matching samples | count before allocating outputs, even outside the GraphQL guard; rejects with `BAD_USER_INPUT` |
| `points`, `roadQualityGrid`, `roadSegments` per request | 2 each | |
| `config` (server Google key) | refused on the public schema | defense in depth for the QA fix |
| Label queue (`labelQueue`, `quickLabel`, undo, re-check) | not on the public schema; `IsAdmin` on the full schema | |

Logs: Google client errors are logged through `secret_scan.redact_secrets`.
`requests` puts the full URL, `key=` included, into connection-error messages.

Coordinate parsing accepts only decimal `lat,lng`, with optional whitespace
around the comma. Numeric alternatives such as `47.5 19.04`, semicolons, explicit
plus signs, Unicode minus signs and N/E prefixes are **rejected**, even inside
the bbox; they never fall through to address geocoding. Real addresses retain
the existing Google path (including addresses abroad). Google location modifiers
and any `name:value` prefix are rejected before address fallback, including
modifiers hiding foreign coordinates. Local requests with
either endpoint a coordinate use at most 1 Directions call; two addresses may
use at most 4 calls on a miss (Directions + 2 Geocoding + Directions). Public
requests always use at most 1 Directions call. The SDK's automatic HTTP/API
retries are disabled in both modes.
Directions and Geocoding share a client with a **2 s connect / 5 s read timeout**
on every HTTP attempt. Timeouts return a generic `UPSTREAM_TIMEOUT` error with
no URL or exception text and stop fallback/retry calls. Both route resolvers
offload blocking Google I/O to a worker thread; `routeAlternatives` also keeps
its synchronous DB session and matching work in that thread.

The combined daily counter (`backend/app/services/directions_quota.py`) follows
the Street View counter's exclusive file lock and atomic JSON replacement.
Days reset at midnight US Pacific time. Local storage is
`DATA_DIR/quota/google_directions.json`; `PUBLIC_READ_ONLY=1` uses
`/tmp/smooth-route/quota/google_directions.json`, so it works with Vercel's
read-only deployment bundle. Optional `GOOGLE_DIRECTIONS_QUOTA_PATH` sets an
alternate counter file (use an absolute, writable path). Corrupt or unwritable
storage blocks calls; exhaustion returns `RESOURCE_EXHAUSTED` with a clear error.
Vercel's filesystem is ephemeral and not shared across instances: this is a
**per-instance, best-effort cap**, lost on replacement/restart and independent
on each instance. The hard cap is the Google Cloud quota in owner checklist
item 3 below; the application counter does not replace it.
Finding 4 remains a documented limitation: there is no deployment-wide atomic
application counter. **Only the separately configured Google Cloud hard quota
caps deployment-wide Google usage**; its dashboard settings have not been
verified by these offline tests. Budget alerts do not enforce a cap.

The validators are plain functions; call them first thing in a resolver when
it is used outside the guard (e.g. a REST endpoint or a renamed argument):
`validate_points_args`, `validate_grid_args`, `validate_segments_args(zoom, bbox)`,
`validate_route_endpoints`, `validate_route_path(path) -> [(lat, lng)]`.
Admin data on a public type: `admin_only_field()` in `permissions.py` (null for
non-admins, no error).

Probe locally without spending quota: `.claude/launch.json` → `api-readonly-8004`
(PUBLIC_READ_ONLY=1, Clerk unconfigured, Google key blanked). Never load-test the
live URLs.

## Owner checklist (dashboards only)

1. **Rotate the Google Maps key** — it was readable anonymously from the live API
   (`/api/v1/config`, GraphQL `config`) since the round-1 launch. Create a new key,
   put it into the Vercel backend env, redeploy, then delete the old key.
2. **Split and restrict keys** (Google Cloud → APIs & Services → Credentials):
   - *Vercel server key*: API restriction = **Directions API + Geocoding API** only.
     An HTTP-referrer restriction does not work for server-side calls, and
     Vercel has no fixed egress IP — so the API restriction + quotas are the guard.
   - *Local Mac key* (`.env`): Street View Static + Metadata, Directions,
     Geocoding; IP restriction if the home IP is static.
   - The frontend needs no Google key (Leaflet tiles, Street View deep links).
3. **Hard quotas** (APIs & Services → each API → Quotas): Directions and
   Geocoding e.g. 300 requests/day and 30/minute; Street View Static per day on
   the local key. These are the real money cap.
4. **Budget alert** (Billing → Budgets & alerts): e.g. $5/month, e-mail at 50/90/100 %.
   Alerts do not stop spending — the quotas do.
5. **Vercel Firewall** (backend project → Firewall): rate-limit `/graphql`, e.g.
   60 requests/min per IP → 429, if the plan offers rate-limit rules; otherwise
   keep Attack Challenge Mode ready for an incident. Hobby has no overage
   billing — abuse means a paused project, not a bill.
6. **Vercel function region** (backend → Settings → Functions): `fra1`, next to
   Neon (Frankfurt). Today the function runs in `iad1`, so every query crosses
   the Atlantic.
7. **Neon read-only role** (SQL editor): a login role with `SELECT` only and
   `ALTER ROLE … SET statement_timeout = '5s'`; use its *pooled* URL as Vercel's
   `DATABASE_URL`. The owner role stays local for `publish.py` only. Also run
   `ALTER DEFAULT PRIVILEGES FOR ROLE neondb_owner IN SCHEMA public GRANT SELECT ON TABLES TO <role>`:
   `GRANT … ON ALL TABLES` covers only existing tables, so without it a later
   migration's table (e.g. `road_segments`) is unreadable. Full SQL:
   `backend/scripts/release_rehearsal.sh` step 3.
8. After DNS (R1.4): `ALLOWED_ORIGINS=https://simaut.hu` only; check that Vercel
   preview deployments are protected or disabled (`git.deploymentEnabled`).
9. Local hygiene: `chmod 600 .env`; reinstall the shared `.venv` from
   `backend/pyproject.toml` when no session is running (it still has
   strawberry-graphql 0.287, starlette 0.50, PyJWT 2.13 with known advisories;
   the deploy set resolves to fixed versions).
