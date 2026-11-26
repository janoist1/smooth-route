# API surface inventory

*Updated: 2026-11-26 (road-segment layer: `roadSegments` / `routeQuality`; `/api/v1/config` removed).*

## Primary product API: GraphQL

The Vite/React frontend uses `/graphql` for points, route processing,
settings, training and review actions. Automatic YOLO marking runs through the
`performReviewAction(action_type: "auto_detect")` mutation; the direct
`detectObjects` mutation stays for programmatic GraphQL consumers.

Read-only RQI diagnostics (D3): the `Point` type also exposes the raw DINO
estimate and the calibrated bad-road probability (`dinoScore`, `dinoPBad`,
derived from `analysisMetadata`); the `rqiModelInfo` query returns the live
artifact's model card (version, recipe, training size, CV metrics) for the
settings UI.

Image age: `Point.captureDate` (`String`, `"YYYY-MM"`, `null` = unknown) is the
Street View panorama's **capture month** from the Metadata API `date` field —
the RQI describes the road as of that month, not as of `createdAt` (our
download time). Readable anonymously and on the read-only deploy (`point`,
`points`, `trainingPoints`). Stored as `street_view_images.capture_date`
(`DATE`, 1st of the month; Alembic `0004`). New points get it from collection
(`route_collector`) and download (`image_downloader`); existing ones from
`backend/scripts/backfill_capture_date.py` (rate-limited, re-runnable, only
looks at `NULL`s). For a point without `pano_id` it only writes a date when the
panorama live today predates our download month — otherwise Google has
replaced the imagery since, and the date is not our image's. `publish.py`
carries the field to Neon. The frontend warns for images older than 4 years
and can optionally dim those points on the map.

## Road-segment layer (`roadSegments`, `routeQuality`)

*Added 2026-11-26.*

Quality aggregated on real road geometry: OpenStreetMap ways, stitched into
roads and cut into pieces of about 150 m, each piece summarising the Street
View frames snapped onto it. Both queries are **anonymous**, work on the
read-only deploy (`PUBLIC_READ_ONLY`), and read only the pre-built
`road_segments` table — no Overpass, model or numpy at request time.

```graphql
type RoadSegment {
  id: ID!                   # "<osmWayId>:<pieceIndex>", stable across rebuilds
  path: [[Float!]!]!        # [[lat, lng], ...]
  rqi: Int                  # 1–4 (1 = excellent, 4 = poor)
  score: Float              # aggregated continuous score, 1–4 scale
  pBad: Float               # 0–1, mean P(bad) of the frames
  confidence: Float!        # 0–1, after the image-age factor
  confidenceLevel: String!  # "high" | "medium" | "low"
  nImages: Int!
  lengthM: Float!
  roadName: String          # OSM name, else ref
  highway: String           # OSM highway class
  captureDateMin: String    # "YYYY-MM", oldest / newest frame on the segment
  captureDateMax: String
}
type RouteQuality {
  totalLengthM: Float!
  coveredLengthM: Float!    # metres of the path that run along a segment with data
  lengthByRqi: [Float!]!    # 4 numbers: metres in class 1, 2, 3, 4
  meanScore: Float          # length-weighted over the covered part; null if none
  worstSegments: [RoadSegment!]!
}
# Query
roadSegments(bbox: [Float!]!, zoom: Int!): [RoadSegment!]!
routeQuality(path: [[Float!]!]!): RouteQuality!
```

**`roadSegments`** — `bbox` = `[minLng, minLat, maxLng, maxLat]` (same order as
`roadQualityGrid`). Returns only segments that have frames. Below **zoom 13**
it returns `[]` (the quality grid is the overview there); at most 5000
segments per call (best-supported first). Geometry is simplified with
`ST_SimplifyPreserveTopology` at half a screen pixel for the zoom, unsimplified
from zoom 18. Only stretches we have frames for exist, so `rqi` / `score` are
in practice never null; the types stay nullable as the contract says.

**`routeQuality`** — `path` = `[[lat, lng], ...]` (at most 20 000 points and
2 000 km: the cost grows with the length, sampled every 10 m). The
path is sampled every 10 m; a sample belongs to the nearest segment within
**15 m** whose direction is within **45°** of the route's (modulo 180°, so
both travel directions count). Samples more than 5 m past a segment's end do
not count, so a data gap is not credited to its neighbours.
`worstSegments`: up to 5, by `score` descending, **excluding
`confidenceLevel = "low"`**, and only segments the route really runs along
(≥ 25 m, or half of a shorter segment). A malformed path is a GraphQL error.

**How a segment's numbers come about** (all tunable in
`backend/config/segment_aggregation.json`; code:
`backend/app/services/segment_aggregation.py`):

- Frame score = `analysis_metadata.dino_score`, else `dino_rqi_score`.
  Frame P(bad) = `analysis_metadata.dino_p_bad`, else 1/0 for RQI ≥ 3 / < 3.
- `aggregator`: `median_score` (default) | `mean_score` |
  `trimmed_mean_score` (`trim_fraction` from each end) | `mean_p_bad` (class
  from the median score, but mean P(bad) ≥ `p_bad_threshold` forces class ≥ 3
  and below it caps the class at 2).
- Class = aggregated score through `thresholds` (`[1.51, 2.47, 3.18]`).
- `confidence = clamp((1 − e^(−n/n_ref)) · e^(−(iqr/spread_ref)²) ·
  (0.5 + 0.5·min(1, margin/margin_ref)), 0, 1) · 0.5^(max(0, age − grace_years)
  / half_life_years)` — `n` frames, `iqr` of their scores, `margin` = distance
  of the aggregated score from the nearest threshold, `age` in years from the
  segment's **newest** capture month (no age factor when unknown).
- `confidenceLevel`: `high` ≥ 0.66, `medium` ≥ 0.33, else `low`; fewer than
  `min_images` (3) frames is always `low` (the class is still reported).

**Data flow.**

- Table `road_segments` (Alembic `0005`, additive): `id`, `osm_way_id`,
  `piece_index`, `geom` (LineString 4326, GiST), `length_m`, `road_name`,
  `highway`, `n_images`, `score`, `rqi`, `p_bad`, `confidence`,
  `capture_date_min/max`, `updated_at`. Derived data — safe to rebuild.
  `osm_way_id` is the smallest OSM way id of the stitched road.
- Builder: `cd backend && ../.venv/bin/python scripts/build_segments.py`
  (`--bbox minLng,minLat,maxLng,maxLat`, `--dry-run`, `--offline`,
  `--no-merge`, `--segment-length`, `--aggregator`). Snaps each scored frame
  to the nearest road within 20 m whose bearing fits the frame heading
  (|Δ| < 45° mod 180), prints match / class / confidence stats, replaces the
  rows in one transaction. Idempotent.
- OSM geometry comes from the public Overpass API, fetched per 0.05° tile
  that contains frames, one request at a time, raw responses cached in
  `data/osm/` — a rebuild normally needs no network. `OVERPASS_URL` overrides
  the endpoint.
- Jobs: a finished route job rebuilds the segments around its new frames, a
  finished analysis job rebuilds all of them (`services/tasks.py`). Best
  effort — if Overpass is unreachable for a new area the refresh is logged and
  skipped, the job still succeeds, and the next builder run catches up.
- Publishing: `scripts/publish.py` full-replaces `road_segments` on the target
  together with `street_view_images` (`--dry-run` reports without touching
  the target). Run the builder before publishing.

**Attribution (required).** The geometry is © OpenStreetMap contributors,
ODbL. Any map that draws `RoadSegment.path` must show
"© OpenStreetMap contributors" (link: `https://www.openstreetmap.org/copyright`),
whichever base map is selected.

## Retained REST endpoints

| Endpoint | Reason |
|---|---|
| `GET /api/v1/points`, `GET /api/v1/points/{id}` | Simple API documented in the README (the static map that also used it is gone) |
| `POST /api/v1/process-route` | Route processing (formerly for the static map) |
| `GET /api/v1/job/{id}` | Job status lookup (formerly for the static map) |
| `GET /api/v1/job/{id}/stream` | SSE status channel of the React frontend |
| `POST /api/v1/job/{id}/stop`, `GET /api/v1/jobs/active` | Job lifecycle and reconnect |

`/images`, `/previews` and `/api/v1/exports` are file-serving endpoints, not
business-API duplicates.

## Removed

`POST /api/v1/inference/detect` is gone: it had no caller, and the GraphQL
`detectObjects` and the product's `performReviewAction` already cover it. There
is no separate REST annotation endpoint.

`GET /api/v1/config` is gone (2026-11-26) and the GraphQL `config` field is
admin-only: both handed the server-side Google Maps key to anonymous callers
(also on the public read-only deploy), and their only consumer, the static
`map.html`, no longer exists.
