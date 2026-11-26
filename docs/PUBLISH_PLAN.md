# Publishing plan — round 1 read-only, round 2 user submissions

*Status 2026-11-26: **round 1 is live** on the Vercel default domains; only R1.4
(DNS + hardening) is open. Round 2 waits until users may submit analyses. Prices
checked 2026-07-03 (sources at the end).*

Work on one phase at a time: read the strategy, your phase, and the shared
sections it points to (data model, quotas/dedup, hardening) — not the other phases.

## Strategy

**Round 1 — read-only (now).** The owner runs the full pipeline locally on request
(Google download + DINO RQI), then `backend/scripts/publish.py` pushes the results
to a hosted read-only DB. The public site only **reads**: map, quality grid, route
display. **No images in the cloud** — point details deep-link to Google Street View.
No public user action → no prod auth, queue or quotas.

**Round 2 — user submissions (later).** Users may request an A→B analysis:
reactivate the finished F1 Clerk auth, add the request flow (admin approval → job →
e-mail) and quotas. Needs an always-on backend (torch + worker); the
Hetzner/Procrastinate/Clerk/R2 analysis below is for this round.

## Round 1 architecture

```
 [owner's Mac: full pipeline]             (local, on request, inside Google free tier)
  Google download + DINO RQI ──publish──▶ [Neon Postgres]  (read-only data)
  (images stay on the Mac)                       ▲
                                                 │ read
  browser ──▶ Vercel #1 frontend (frontend/, Vite SPA)
          └─▶ Vercel #2 API (backend/, same app.main:app, PUBLIC_READ_ONLY=1, torch-free)
  point details ──▶ free Google Maps Street View deep-link (no stored image)
```

Target domains: `simaut.hu` → Vercel #1, `api.simaut.hu` → Vercel #2. The frontend
calls `${VITE_API_URL}/graphql` (empty in dev → relative, Vite proxy to :8000).
Both projects auto-deploy on every push to `master`.

| Layer | Choice | Monthly |
|---|---|---|
| Frontend + read API | Vercel Hobby | $0 |
| Read-only DB | Neon free tier (PostGIS, EU, scale-to-zero) | $0 |
| Compute (analysis) | owner's Mac, on request | $0 |
| Images | none — Street View deep-link | $0 |
| Google Maps | inside free tier (downloads local; Directions proxied) | $0 |
| Domain | `simaut.hu` | ~€1 |

### Round 1 phases

- **R1.1 — Street View link instead of stored image (DONE, `1f10b25`).** `pano_id`
  column (Alembic 0003); `Point.streetViewUrl` (`api=1&map_action=pano&pano=…`,
  fallback `viewpoint=lat,lng`); the detail card links out instead of `<img>`.
- **R1.2 — read-only mode + Vercel packaging (DONE, `63c1dd2`).** `PUBLIC_READ_ONLY`
  mounts the query-only `read_schema`, narrows CORS to `ALLOWED_ORIGINS`, keeps
  imports torch-free; `backend/requirements.txt`, `backend/api/index.py`,
  `backend/vercel.json`, `frontend/vercel.json`. API env: `PUBLIC_READ_ONLY=1`,
  `RUN_MIGRATIONS_ON_STARTUP=false`, `DATABASE_URL` (Neon), `GOOGLE_MAPS_API_KEY`,
  `ALLOWED_ORIGINS`.
- **R1.3 — Neon + publish script (DONE, live).** `backend/scripts/publish.py`
  migrates the target with Alembic (fresh Neon: `CREATE EXTENSION postgis`), then
  full-replaces the public columns of `street_view_images` (`image_url`, `location`
  → NULL). Target from `PUBLISH_DATABASE_URL` (unpooled Neon URL; never in the repo):
  `cd backend && PUBLISH_DATABASE_URL='postgresql://…' ../.venv/bin/python scripts/publish.py`.
- **R1.4 — DNS + hardening (OPEN, owner's infra steps).**
  - [ ] DNS: `simaut.hu` + `www` → Vercel #1, `api.simaut.hu` → Vercel #2.
  - [ ] Then set `VITE_API_URL=https://api.simaut.hu` and
        `ALLOWED_ORIGINS=https://simaut.hu`; redeploy both.
  - [ ] Google key HTTP-referrer/IP restriction + GCP budget alert; GraphQL
        introspection off in prod (nice-to-have).
  - **Done when:** `simaut.hu` serves the read-only map, Directions go through
    `api.simaut.hu`, no key leaks.

## Round 2 architecture (always-on backend)

```
 browser ──▶ Cloudflare Pages (static frontend)
         ──▶ api.<domain> (CF proxy) ──▶ Hetzner VPS, docker compose:
                 Caddy (TLS) → FastAPI API · worker (torch, Procrastinate) · PostGIS
             Clerk (auth: e-mail+password, Google)   Cloudflare R2 (images + DB backups)
```

| Layer | Choice | Monthly |
|---|---|---|
| Frontend | Cloudflare Pages | €0 |
| API + worker + DB | Hetzner CX32 (4 vCPU / 8 GB); CX22 possible but tight with torch | ~€6.80 |
| Auth | Clerk free (50k MRU) | €0 |
| Images + backup | Cloudflare R2 (10 GB free, zero egress) | €0 |
| Queue | Procrastinate (on the same Postgres) | €0 |
| Google Maps | quotas keep us under the free tier | €0 (above: $7/1000 images) |
| Sentry + UptimeRobot | free tiers | €0 |
| **Total** | | **~€8** |

### Why these choices

- **Hosting:** the backend needs torch + transformers + ultralytics (5–7 GB image,
  2–4 GB RAM), PostGIS and long jobs → no serverless for the heavy part. Hetzner is
  the cheapest with full control (we own backups, F6). Rejected: Supabase+Fly (free DB
  pauses after 7 idle days, 1 GB storage too small, an always-on 4 GB Fly worker costs
  more than the whole VPS); AWS (RDS+Fargate alone exceed budget, heavy ops);
  Render/Railway (torch-sized plans cost more); home machine + tunnel (uptime = your
  laptop). Put the free CF proxy in front of the VPS (WAF, DDoS, hides origin IP).
- **Auth:** Clerk — ready-made React components, Google OAuth, sends verification
  and reset e-mails itself; the backend only verifies JWTs (JWKS). Our own `users`
  table owns roles/quotas/jobs, so switching provider = replacing one dependency.
  Fallbacks: Firebase Auth (never pauses, more UI work), FastAPI-Users (self-host).
- **Queue:** Procrastinate — no new infra, LISTEN/NOTIFY pickup, retries, locks,
  transactional enqueue. Redis+Celery adds a container for no gain; `threading.Thread`
  (today) dies on restart and has no retry.

### Google Maps cost model (the cornerstone)

- Street View Static: **$7/1000, 10 000/month free**.
- Street View **Metadata: free, unlimited** — returns `pano_id`, so dedup is free.
- Directions/Routes: $5/1000, 10 000/month free.
- Per-API daily quota caps in the GCP console are the **hard** cost ceiling.

Set the global monthly budget below the free tier (e.g. 9 000 new images/month) →
Google cost $0; going above is a deliberate decision.

## Shared: central collection and dedup

Goal: pay for each point's image exactly once, shared across users.

1. **Pano level (the real key).** Before fetching, a free metadata call gets
   `pano_id`; if `(pano_id, heading_bucket)` (15° buckets) exists, reuse it. Paid
   fetches only for new panoramas.
2. **Spatial (PostGIS).** Before sampling a route, reuse existing points within
   ~10 m of the polyline (heading ±30°) — no metadata call needed.
3. **Concurrency.** Workers claim panos with `INSERT … ON CONFLICT DO NOTHING` and
   process with `SELECT … FOR UPDATE SKIP LOCKED` (start with one worker).

**Re-analysis:** store `model_version` with each result; after a new model passes
the `ml/` gate, an admin batch job re-scores existing images without downloading.

## Shared: quotas and cost protection

1. **GCP hard cap:** daily quota on Street View Static + Directions (e.g. 300
   images/day) + budget alert — holds even if the app misbehaves.
2. **Global monthly budget in the app** (e.g. 9 000 new images/month); when full, jobs
   wait in a "waiting for quota" state instead of failing.
3. **Per-user quota** counting only *new* (non-dedup) downloads, e.g. 100/day and
   1 000/month; admins unlimited; configured via `core/settings_registry.py`.
4. **Rate limit:** slowapi per user/IP on mutations + a CF rate-limit rule.

Accounting: `usage_events(user_id, kind: sv_image_fetch | directions_call | analysis,
qty, job_id, created_at)` drives quota checks, the "remaining today" UI and the admin
usage view.

## Shared: roles

| Role | Can |
|---|---|
| anonymous | view the public map (read-only) — decided: yes |
| `user` | map + start route collection (with quota), own jobs |
| `admin` | everything: labelling/review, training, settings, all jobs, quota overrides, usage view |

Labelling surfaces must stay admin-only: label quality is the model's foundation.

## Shared: data model changes

```sql
-- new
users(id uuid PK, clerk_id text UNIQUE, email text, role text DEFAULT 'user', created_at timestamptz)  -- done (0002)
usage_events(id bigserial PK, user_id uuid FK, kind text, qty int,
             job_id text NULL, created_at timestamptz)  -- index (user_id, created_at)
-- extend
jobs               + user_id FK, job_type text, params jsonb        -- round 2
street_view_images + pano_id text (index)                           -- done (0003)
                   + heading_bucket smallint, model_version text,
                     UNIQUE (pano_id, heading_bucket)                -- round 2 dedup
```

Never put a Street View **Static** URL into an `<img>` — it bills per view and
exposes the key. Schema changes go through Alembic (`backend/alembic/`).

## Shared: security hardening (before round-2 launch)

- [ ] CORS: drop `"*"` from the local-dev origin list for any non-read-only prod
      deploy (`backend/app/main.py`; read-only mode already uses `ALLOWED_ORIGINS`).
- [ ] GraphQL introspection + GraphiQL off in prod; `strawberry-graphql[debug-server]`
      dev-only.
- [ ] Dockerfile: drop `--reload` from `CMD`, non-root user, multi-stage, pinned deps.
- [ ] Google key: server key with IP restriction, daily quota caps, budget alert.
- [ ] Secrets: `.env` with mode 600 on the VPS, GitHub Secrets in CI, never in the repo.
- [ ] Replace leftover `print("DEBUG…")` with structured logging.
- [ ] REST `/api/v1/*` behind the same JWT dependency as GraphQL.

## Shared: Google ToS note

The ToS restricts long-term storage/caching of Street View content. Round 1 avoids
it: the public site shows only **derived data** (RQI colours, grid, stats) plus a link
to Google's own Street View; locally downloaded training images never leave the
Mac. If round 2 needs inline panoramas, use the official Maps JS
`StreetViewPanorama` embed (free up to 5k loads/month), not re-served stored images.

## Round 2 phases

Each phase ships on its own with green gates ([AGENTS.md](../AGENTS.md)).

### F0 — Prod foundation (1–2 days)
- [x] Alembic with baseline migration (done with F1: 0001 baseline, 0002 users;
      startup runs `ensure_database_schema()` under `pg_advisory_lock` and stamps
      pre-Alembic DBs; `create_all` only in tests).
- [ ] Prod config (`ENV=prod`): narrow CORS, introspection/GraphiQL off, no debug logs.
- [ ] Prod Dockerfile (multi-stage, non-root, no `--reload`) + `docker-compose.prod.yml`
      (api + worker + db + caddy).
- [ ] `print` → `logging` in the services layer.
- **Done when:** the prod compose serves the frontend build locally; gates green.

### F1 — Auth and roles, Clerk (DONE; inactive in prod until round 2)
- Backend: JWKS JWT dependency (`app/core/auth.py`), `users` table with JIT
  provisioning, `role` = `user`/`admin` (admin set by SQL); Strawberry
  `IsAuthenticated` / `IsAdmin`; training/review/settings queries and mutations
  admin-only; route start and `getRoute` (paid Directions) user-only; `me` query;
  the two mutating REST endpoints user-only, map reads anonymous.
- Frontend: `modules/auth/` — `@clerk/clerk-react` sign-in/up modal, user menu,
  Apollo auth link; admin menus/routes hidden via `me`.
- Local dev: `AUTH_MODE=disabled` (everyone is admin). Dev Clerk instance keys:
  `CLERK_SECRET_KEY`, `CLERK_ISSUER` in root `.env`, `VITE_CLERK_PUBLISHABLE_KEY` in
  `frontend/.env`. Gotcha: the default Clerk session token has **no e-mail** — add it
  via a JWT template or fetch it from the Clerk API.
- Left for F5: own Google Cloud OAuth consent + client id for the prod instance; one
  manual click-through test of Google login.

### F1.5 — Map quality grid (DONE, 2026-07-03)
- `roadQualityGrid(zoom, bbox)`: zoom-dependent grid, **mean** RQI per cell
  (`COALESCE(dino_rqi_score, rqi_score)`), anonymous; helpers in
  `app/services/map_aggregation.py`. Frontend `QualityGridLayer` (canvas): zoom < 14
  grid, ≥ 14 raw clickable points (limit 20 000, `preferCanvas`).
- Lesson: a classic heatmap (leaflet.heat) **sums** intensities, so colour encoded
  coverage, not quality. Use per-cell means: colour = quality, filled cells = coverage.
- Optional polish: canvas upscale + blur to make the grid less blocky.

### F2 — Request-based coverage + user-bound jobs (3–4 days)
New coverage (A→B collection + inference) goes through **request → admin approval →
e-mail**, not self-service quota; route planning on already analysed roads stays
self-service for signed-in users.
- [ ] `analysis_request` table: `user_id`, `origin`, `destination`, `status`
      (`pending/approved/running/done/rejected`), `note`, `job_id`, `created_at`.
- [ ] Hungary geofence (bounding box first): submissions and `getRoute` reject non-HU A/B.
- [ ] GraphQL: `submitAnalysisRequest`, `myRequests` (user); `pendingRequests`,
      `approveRequest`, `rejectRequest(reason)` (admin); approval starts the process-route
      job bound to `user_id`/`request_id`.
- [ ] Procrastinate + worker entry point (same image, different CMD); replace the
      thread start in `tasks.py`/`job_runner.py` with `defer`; pipeline steps
      (collect → download → analyze) as retrying tasks.
- [ ] `jobs` + `user_id`, `job_type`, `params`; keep SSE progress; worker concurrency 1.
- [ ] Completion e-mail via a pluggable provider (SMTP or e.g. Resend; key from env;
      console fallback in dev).
- **Done when:** a HU request is approved → job runs → request `done` → requester gets
  the e-mail; a non-HU request is rejected; a job survives an API restart.

### F3 — Central collection: dedup + quotas (3–5 days)
- [ ] `heading_bucket` + `model_version`, unique index; backfill with free metadata calls.
- [ ] Metadata-first download path: paid fetch only for new `(pano_id, bucket)`.
- [ ] Spatial reuse along the route corridor (PostGIS).
- [ ] `usage_events` + quota service (user daily/monthly, global monthly) via settings;
      full quota → job waits, user sees a clear status.
- [ ] Claim (`ON CONFLICT DO NOTHING`) + `SKIP LOCKED`.
- [ ] Frontend: remaining-quota display; "X points already known, Y new" on the job card.
- **Done when:** a second job on the same stretch makes **0** paid Google calls; quota
  overrun blocks and is communicated.

### F4 — Images on R2 (1–2 days)
- [ ] Private R2 bucket + boto3; `image_url` → object key; migrate `data/images/` (~1.1 GB).
- [ ] Short-lived presigned URLs for signed-in users; worker downloads → analyses →
      keeps no local copy (or an LRU cache).
- [ ] `ml/` can still work locally (sync script from R2).
- **Done when:** a fresh deploy with an empty disk is fully functional, training works
  from R2.

### F5 — Prod infra + CI/CD (1–2 days)
- [ ] Hetzner CX32 (EU) + compose; firewall 80/443 + SSH only.
- [ ] Domain + Cloudflare DNS with proxy on.
- [ ] Frontend on Cloudflare Pages (`VITE_API_URL` → prod API, free PR previews).
- [ ] GitHub Actions: gates → image build → GHCR → SSH deploy
      (`docker compose pull && up -d`), Alembic migration in the deploy step.
- [ ] Clerk prod instance on the own domain; GCP key IP restriction + daily caps.
- **Done when:** prod URL has TLS; push to `master` deploys; staging (local prod
  compose) and prod run the same image.

### F6 — Operations: backup + observability (1–2 days)
- [ ] Nightly `pg_dump` → R2 (14-day retention) + a **documented restore test**.
- [ ] Weekly Hetzner snapshot.
- [ ] Sentry (backend + frontend), UptimeRobot on `/health`.
- [ ] Admin usage view: daily/monthly Google calls, top users, budget status.
- **Done when:** restore test passes; alerts fire on outage; admin sees budget usage.

Round 2 estimate: ~11–18 working days.

## Open product questions (owner decides)

1. Quota numbers: are 100 new images/day/user and 9 000/month global right?
2. ToS stance: OK with "images private, derived data public"?
3. Domain: register `simaut.hu` (also needed for the Clerk prod instance).

## Sources (checked 2026-07-03)

- Google Maps pricing (Street View Static $7/1k + 10k free; metadata free; Directions
  $5/1k + 10k free): <https://developers.google.com/maps/billing-and-pricing/pricing>
- Supabase free tier (500 MB DB, 1 GB storage, pauses after 7 idle days): <https://supabase.com/pricing>
- Hetzner Cloud prices (note the 2026-06-15 adjustment): <https://www.hetzner.com/cloud/regular-performance>,
  <https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/>
- Cloudflare R2 (10 GB free, zero egress): <https://developers.cloudflare.com/r2/pricing/>
- Clerk (free tier raised to 50k MRU, 2026-02): <https://clerk.com/pricing>
- Procrastinate: <https://github.com/procrastinate-org/procrastinate>
