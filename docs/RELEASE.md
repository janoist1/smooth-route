# Release runbook: Neon publish + master deploy

*Written 2026-11-26 for the first segment release (Alembic 0004–0010, road
segments, scale flip to 5 = Kiváló, security limits, key fix). Rehearsed
end-to-end locally (see the last section). Owner approval: board ticket T-21.*

**Why the order matters.** Production `master` still serves the Google key
(`/api/v1/config`) and reads the round-1 schema (Neon at Alembic 0003, 1 = best).
The new code needs 0004–0010 on Neon, and the scale flip changes what the numbers
mean. So: new key ready but unused → Neon migrated + republished → verified →
`master` pushed → smoke. Between the publish (step 4) and the end of the deploy
(step 6), the old live site shows **inverted colours** (new data, old scale).
Run steps 4–6 back to back, at a quiet hour, so that window stays a few minutes.

Run everything from `backend/` in a checkout of **the exact release commit**
(the commit that goes to `master`), with the local dev DB up.

## 0. Preconditions (no outside calls)

- [ ] Release commit chosen: `claude/analysis-layer` after the last merge; gates green
      on it (AGENTS.md → Gates, both backend dependency sets: see
      [DEVELOPMENT.md](../DEVELOPMENT.md)).
- [ ] No collection job running. The new frames have been post-processed
      (frame_quality → `rescore_dino.py` → `build_segments.py`, see DEVELOPMENT.md), so
      points and segments come from the same state. Publish ships the **whole**
      local table; if the new Budapest frames should wait (T-36 QA), decide that now.
- [ ] Local DB at head: `../.venv/bin/python -m alembic current` → `0010 (head)`.
- [ ] Get Neon's **direct (unpooled)** URL from Vercel → backend project → Settings →
      Environment Variables (`DATABASE_URL_UNPOOLED`), or from Neon → Connect with pooling
      off. Keep it out of shell history:
      `read -rs PUBLISH_DATABASE_URL && export PUBLISH_DATABASE_URL`.
- [ ] Note the time (T0). It's the restore point for Neon's own point-in-time restore.
- [ ] Backend environment: `GOOGLE_DIRECTIONS_DAILY_CAP=300` (combined Directions
      + Geocoding attempts per Pacific day; `0` blocks all). With
      `PUBLIC_READ_ONLY=1`, the counter defaults to
      `/tmp/smooth-route/quota/google_directions.json`; optional
      `GOOGLE_DIRECTIONS_QUOTA_PATH` overrides the file with an absolute writable
      path. Vercel storage makes this a per-instance, best-effort cap. Set the
      hard Directions/Geocoding quotas in Google Cloud too
      ([SECURITY.md](SECURITY.md#owner-checklist-dashboards-only), item 3).

## Steps

| # | Who | Do | Check | Rollback |
|---|---|---|---|---|
| 1 | owner | **Done 2026-11-27.** Server key `simaut-prod-server` (Directions + Geocoding only); project quotas Directions and Geocoding v3 300/day + 30/min. The owner pastes it into Vercel → backend → Env → `GOOGLE_MAPS_API_KEY` (Production). **Do not redeploy:** old `master` would expose the new key at `/api/v1/config` too. The step-6 deploy is the first one that reads it. | Vercel env holds the new key; no deploy since. | — (the old key is gone, see step 8). |
| 2 | owner | **Neon snapshot:** Neon console → Branches → create branch `pre-release-YYYYMMDD` from `main` (instant, copy-on-write). | Branch listed. | — (this *is* the rollback anchor). |
| 3 | owner/lead | **Dry run:** `../.venv/bin/python scripts/publish.py --dry-run` | Prints `target revision: 0003; pending migrations: 0004, 0005, 0006, 0007, 0008, 0009, 0010`, the target row counts and what would be published. **No `SECRET` lines.** It only reads Neon. | Nothing to roll back. Anything unexpected (other revision, `Refusing`, tables without `alembic_version`) → stop. |
| 4 | owner/lead | **Publish:** `../.venv/bin/python scripts/publish.py`. Runs Alembic 0004→0010 on Neon (0006 mirrors the round-1 values to 5 = best), then replaces both tables in **one transaction** (DELETE + INSERT: live readers keep the old rows until COMMIT). | Ends with `published N rows … and M road segments`. Re-running the dry run says `target revision: 0010; pending migrations: none`. | Scripted: `DATABASE_URL="$PUBLISH_DATABASE_URL" ../.venv/bin/python -m alembic downgrade 0003`. This flips the data back to 1 = best and drops `road_segments` and `capture_date`, which is exactly what old `master` reads (rehearsed). Or restore `main` from the step-2 branch / to T0 in the Neon console. |
| 5 | owner/lead | **Verify the new code against Neon before pushing:** run the read-only API locally against Neon's pooled URL (`DATABASE_URL` in Vercel; `read -rs NEON_POOLED_URL && export NEON_POOLED_URL`) and smoke it. Reads only, no Google call: `PUBLIC_READ_ONLY=1 RUN_MIGRATIONS_ON_STARTUP=false GOOGLE_MAPS_API_KEY= ALLOWED_ORIGINS=https://simaut.hu DATABASE_URL="$NEON_POOLED_URL" uv run --no-project --with-requirements requirements.txt python -m uvicorn app.main:app --port 8006`, then `python3 scripts/smoke_public_api.py http://127.0.0.1:8006 --origin https://simaut.hu` | `all checks passed` (≈24 checks: points + captureDate, roadSegments, scale direction, routeQuality, grid, introspection/config/mutations refused, no key in any body). | Step 4's rollback, then stop. |
| 6 | owner | **Deploy:** merge the release commit into `master` and push (owner's approval). Both Vercel projects build from `master`. Watch **both** to *Ready* in the Vercel dashboard. | Both deployments Ready, no build error. | Vercel → each project → Deployments → previous production → **Instant Rollback**, *both* projects. Then do step 4's rollback too: old code + new data = inverted colours. Later pushes are not auto-promoted until you promote again. A `git revert` on `master` is only needed for the next attempt. |
| 7 | owner/lead | **Post-deploy smoke:** `python3 scripts/smoke_public_api.py https://smooth-route-api.vercel.app --origin https://smooth-route-chi.vercel.app` (about 20 normal reads; never calls `getRoute`). Then by hand in a browser: https://smooth-route-chi.vercel.app shows dots + the segment layer around Budapest; blue = good (5), red = bad (1); a segment card and a point card open; the legend reads 5 = Kiváló. One route plan if you want to see `getRoute` (one Directions call on the new key). `curl -sI https://smooth-route-chi.vercel.app` shows `x-frame-options: DENY`. | All pass. In Google Cloud → Metrics, calls arrive on the **new** key. | Step 6's rollback (both projects + step 4). |
| 8 | owner | **Done early, 2026-11-27:** the old key was deleted (restorable for 30 days under Credentials → *Restore deleted credentials*) and a local key `simaut-local-mac` (Street View Static, Directions, Geocoding) was created for the root `.env`. Until step 6, route planning on the live site fails (old `master` still holds the deleted key); points and segments still load. | Local `make dev` route download works with the new `.env` key. | — |

After step 8, move T-21 to done. Still open on [SECURITY.md](SECURITY.md#owner-checklist-dashboards-only):
function region `fra1`, the Neon read-only role, budget alert, firewall rule, DNS (R1.4).

## Smoke checks, what they prove

`backend/scripts/smoke_public_api.py` uses only the stdlib and exits 1 on any failure:
health + security headers · REST, `/docs` and `/openapi.json` return 404 · GraphQL via
GET refused · introspection off · `config` refused · mutations refused · CORS allows the
frontend origin and refuses a foreign one · `points` in the Budapest bbox, values 1–5,
`captureDate` present (0004) · point detail has no `imageUrl`, has `streetViewUrl` ·
`roadSegments` present (0005 + publish), values 1–5 · **scale direction**: segments
rated ≤ 2 carry the higher `pBad`. This catches a flip that ran twice or not at all ·
`roadQualityGrid` · `routeQuality` along a rated segment is covered · an oversized
path is refused · no response body contains anything key-shaped.

## Local rehearsal (no Neon, Vercel or Google)

```bash
cd backend && scripts/release_rehearsal.sh       # ~1 min; container sr-release-rehearsal on 127.0.0.1:5440
```

The script builds the round-1 state: Alembic 0003, schema-only `pg_dump` restored
as a **non-superuser** owner with PostGIS pre-installed (as on Neon), and the
`alembic_version` row copied. It seeds the local points in the old numbering and
creates the read-only web role (SECURITY.md item 7) *before* the upgrade. Then it
runs steps 3–4 with the same commands.

Start the API with launch config `api-rehearsal-8006` (Vercel dependency set, connects
as the read-only role) and run step 5's smoke script against `http://127.0.0.1:8006`.
`scripts/release_rehearsal.sh --down` removes the container.

Rehearsal 2026-11-26 (rerun with 0007 for T-45: 18,798 points + 1,500 segments, 0003 → 0007,
smoke green): 18,301 points + 1,360 segments published, 0003 → 0006, all 22
smoke checks pass, rollback `downgrade 0003` restores the round-1 schema with the
old numbering. A republish under a live reader: the slowest read took 110 ms, and the
reader only ever saw the old or the new row count. What it found, now fixed:

- **Stale DB connections → empty map.** The app engine had no `pool_pre_ping`. After
  the DB dropped idle connections (Neon does this when an idle compute suspends),
  the next request failed and showed up masked as an empty map. Fixed in
  `app/core/database.py`.
- **Publish froze the live site.** `TRUNCATE` held an exclusive lock for the whole
  upload, so every public read waited. It now uses DELETE inside the same transaction.
- **Blind dry run.** `--dry-run` now also reads the target's revision, pending migrations
  and row counts. Publish refuses a target with tables but no `alembic_version` row,
  or at a revision this checkout doesn't know.
- **Read-only role misses new tables.** `GRANT SELECT ON ALL TABLES` covers only
  existing tables. Without `ALTER DEFAULT PRIVILEGES`, a role created before 0005
  can't read `road_segments` (SECURITY.md item 7 updated).
- Neon URLs with a `%` in the password broke Alembic's config parser. They're now escaped.

Not covered locally: Neon's PgBouncer pooler, Postgres 17 (the rehearsal uses
`postgis/postgis:16-3.4`), Vercel's file bundling. Step 7 covers those.
