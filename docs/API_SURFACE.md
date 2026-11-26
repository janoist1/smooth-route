# API surface inventory

*Updated 2026-11-26.* GraphQL is the product API; REST is down to the job stream.

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

## Road-segment layer (`roadSegments`, `routeQuality`, `segmentFrames`)

*Added 2026-11-26.*

Quality aggregated on real road geometry: OpenStreetMap ways, stitched into
roads and cut into pieces of about 200 m, each piece summarising the Street
View frames snapped onto it. All of it is **anonymous**, works on the
read-only deploy (`PUBLIC_READ_ONLY`), and reads only the pre-built
`road_segments` table — no Overpass, model or numpy at request time.

```graphql
type RoadSegment {
  id: ID!                   # "<osmWayId>:<pieceIndex>", stable across rebuilds
  path: [[Float!]!]!        # [[lat, lng], ...]
  rqi: Int                  # RQI level, 5 = Kiváló … 2 = Rossz (see "The RQI scale" below)
  score: Float              # aggregated continuous score, same scale
  pBad: Float               # 0–1, mean P(bad) of the frames
  confidence: Float!        # 0–1, after the image-age factor
  confidenceLevel: String!  # "high" | "medium" | "low"
  nImages: Int!
  lengthM: Float!
  roadName: String          # OSM name, else ref
  highway: String           # OSM highway class
  captureDateMin: String    # "YYYY-MM", oldest / newest frame on the segment
  captureDateMax: String
  confidenceReason: String  # "few_images" | "disagreement" | "near_threshold" | "old_images" | "unlabelled_area"; null when high
  streetViewUrl: String     # Street View deep link at the piece midpoint
}
type RouteQuality {
  totalLengthM: Float!
  coveredLengthM: Float!    # = sum(lengthByRqi)
  lengthByRqi: [Float!]!    # metres per class, BEST FIRST: Kiváló, Jó, Közepes, Rossz
  meanScore: Float          # length-weighted, on the score scale; null if nothing covered
  worstSegments: [RoadSegment!]!
}
# Query
roadSegments(bbox: [Float!]!, zoom: Int!): [RoadSegment!]!
routeQuality(path: [[Float!]!]!): RouteQuality!
segmentFrames(segmentId: ID!): [Point!]!
# Point
segmentId: ID
```

**`roadSegments`** — `bbox` = `[minLng, minLat, maxLng, maxLat]` (same order as
`roadQualityGrid`). Returns only segments that have frames. Below **zoom 13**
it returns `[]` (the quality grid is the overview there); at most 5000
segments per call (best-supported first). Geometry is simplified with
`ST_SimplifyPreserveTopology` at half a screen pixel for the zoom, unsimplified
from zoom 18. Only stretches we have frames for are stored, so `rqi` / `score`
are in practice never null; the types stay nullable as the contract says.

- `confidenceReason` — the factor of the confidence formula that limits it
  most (the smallest of the four factors); `few_images` whenever the segment
  has fewer than `min_images` frames; `unlabelled_area` when the
  unlabelled-area cap (below) lowered it; `null` for `confidenceLevel = "high"`.
- `streetViewUrl` — same scheme as `Point.streetViewUrl`
  (`…/maps/@?api=1&map_action=pano&viewpoint=<lat>,<lng>&heading=<h>&pitch=-20`),
  at the middle of the unsimplified piece, heading along the road. Free link,
  no API call. (It is a viewpoint link: Google picks the nearest panorama.)

**`routeQuality`** — `path` = `[[lat, lng], ...]` (at most 20 000 points and
2 000 km: the cost grows with the length, sampled every 10 m). The
path is sampled every 10 m; a sample belongs to the nearest segment within
**15 m** whose direction is within **45°** of the route's (modulo 180°, so
both travel directions count). Samples more than 5 m past a segment's end do
not count, so a data gap is not credited to its neighbours.

- `coveredLengthM` is by definition `sum(lengthByRqi)` — length that runs
  along a segment without a class is not "covered".
- `meanScore` is the length-weighted mean of the segments' `score` over the
  covered part; `null` when `coveredLengthM` is 0.
- `worstSegments`: up to 5, **worst first**, **excluding
  `confidenceLevel = "low"`**, only segments the route really runs along
  (≥ 25 m, or half of a shorter segment). Same `id`s as `roadSegments`.
- A malformed path is a GraphQL error.
- Stays anonymous even though `getRoute` needs auth outside read-only mode.

**`segmentFrames(segmentId)` / `Point.segmentId`** — the frames a segment was
aggregated from (ordered along it), and the segment a frame belongs to (`null`
if none). The link is not stored: it is re-derived with the builder's own rule
(nearest segment within 20 m whose direction fits the frame heading), so
frames of a parallel or crossing road are not picked up. Only frames the
builder uses are listed (scored, not marked unusable). `Point.segmentId` costs
one small query per point — request it on a single `point`, not on a long
`points` list.

**How a segment's numbers come about** (all tunable in
`backend/config/segment_aggregation.json`, currently the ML recipe from
`ml/segment_recipe.json`; code: `backend/app/services/segment_aggregation.py`):

- Frame score = `analysis_metadata.dino_score`, else `dino_rqi_score`.
  Frame P(bad) = `analysis_metadata.dino_p_bad`, else 1/0 for a bad / good
  ordinal class. Frames with `analysis_metadata.frame_quality.usable = false`
  are skipped (no such key → used).
- The ordinal fallback is a stopgap: an integer class used as a score lands
  on (or next to) a class threshold and reads as "near_threshold".
  `backend/scripts/rescore_dino.py` re-scores stored frames with the live
  artifact (same inference path as the product, raw images, local device) and
  writes `dino_score`, `dino_p_bad` and the class; the class a frame had
  before is kept once in `analysis_metadata.dino_rqi_score_prev`, and
  `analysis_metadata.dino_artifact` records which artifact produced the
  numbers. Resumable, `--dry-run`; take a DB backup first and rebuild the
  segments afterwards.
- `aggregator`: `median_score` (current) | `mean_score` |
  `trimmed_mean_score` (`trim_fraction` from each end) | `mean_p_bad` (class
  from the median score, but mean P(bad) ≥ `p_bad_threshold` forces a bad
  class and below it a good one).
- Class = aggregated score through `thresholds`.
- `confidence = clamp((1 − e^(−n/n_ref)) · e^(−(iqr/spread_ref)²) ·
  (0.5 + 0.5·min(1, margin/margin_ref)), 0, 1) · 0.5^(max(0, age − grace_years)
  / half_life_years)` — `n` frames, `iqr` of their scores, `margin` = distance
  of the aggregated score from the nearest threshold, `age` in years from the
  segment's **newest** capture month (no age factor when unknown).
- `confidenceLevel`: `high` ≥ `confidence.high`, `medium` ≥
  `confidence.medium`, else `low`; fewer than `min_images` frames is always
  `low` (the class is still reported).
- `unlabelled_area` (`radius_km` 3, `cap_level` medium): a segment with no
  human-labelled frame within the radius is capped at the top of that level —
  a product honesty rule, not a fitted factor (measured: distance to labels does
  not predict error, see [MODEL_EXPERIMENTS.md](MODEL_EXPERIMENTS.md)). Stored
  as `road_segments.unlabelled_area` (Alembic `0007`).

**The RQI scale.** The canonical definition is
[shared/rqi_scale.json](../shared/rqi_scale.json) (rules: [shared/README.md](../shared/README.md)):
5 = Kiváló, 4 = Jó, 3 = Közepes, 2 = Rossz, 1 = Nagyon rossz since 2026-11-26.
The segment layer states it for itself in its config — `thresholds` plus

```json
"scale": {"classes": [2, 3, 4, 5], "higher_is_worse": false, "bad_class": 3}
```

— interpreted only by `RqiScale` in `segment_aggregation.py` (`classes` =
labels by ascending score; `bad_class` and everything worse is "bad"). No other
segment code compares a score or class to a literal. A backend test
(`test_rqi_scale.py`) keeps this block equal to the canonical scale and the
thresholds equal to the ML recipe (`ml/segment_recipe.json`, severity numbering)
mirrored; `scripts/sync_rqi_scale.py --flip` mirrors both files together.
`lengthByRqi` is always best first and `worstSegments` worst first, whichever
way the numbers run. Both keys are required: a missing or invalid config file
is an error, not a silent default. Stored values were converted by Alembic
`0006` (new = 6 − old) on 2026-11-26.

**Data flow.**

- Table `road_segments` (Alembic `0005`, additive): `id`, `osm_way_id`,
  `piece_index`, `geom` (LineString 4326, GiST), `length_m`, `road_name`,
  `highway`, `n_images`, `score`, `rqi`, `p_bad`, `confidence`,
  `unlabelled_area` (`0007`), `capture_date_min/max`, `updated_at`. Derived data — safe to rebuild. Only
  pieces with frames are stored. `osm_way_id` is the smallest OSM way id of
  the stitched road.
- Builder: `cd backend && ../.venv/bin/python scripts/build_segments.py`
  (`--bbox minLng,minLat,maxLng,maxLat`, `--dry-run`, `--offline`,
  `--cached-only`, `--no-merge`, `--segment-length`, `--aggregator`).
  Consecutive OSM ways of one road (same name + class, unique continuation at
  the node) are stitched first; each scored frame is snapped to the nearest
  road within 20 m whose bearing fits the frame heading (|Δ| < 45° mod 180);
  prints match / class / confidence stats; replaces the rows in one
  transaction. Idempotent. A `--bbox` run rewrites only the roads touching the
  box and turns itself into a full rebuild when the OSM tiles, the config or
  the engine changed since the last full one. **Re-run it after changing the
  config.**
- OSM geometry comes from the public Overpass API, fetched per 0.05° tile
  that contains frames, one request at a time, raw responses cached in
  `data/osm/` — a rebuild normally needs no network. `OVERPASS_URL` overrides
  the endpoint. `--cached-only` builds a partial layer from the cached tiles
  when Overpass is slow or down.
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

## Label queue / quick-rate screen (admin-only, 2026-11-26)

Labelling at scale: `labelQueue` picks the unlabelled frames (image on disk,
no `manual_rqi`) whose label helps the model most, and `/training/quick`
("Gyors címkézés") rates them one tap at a time. Own resolver module
(`app/graphql/label_queue.py`), merged into the full schema in `schema.py`; it
is **not** on the public read schema.

| Operation | Purpose |
|---|---|
| `labelQueue(strategy: MIXED\|UNCERTAIN\|DIVERSE, limit, excludeIds)` | next frames + why (`reason`, `area`, `boundary`, `uncertainty`, `cellLabels`) + the model guess (`modelScore/modelRqi/modelPBad`, hidden in the UI until rated) + `stats` |
| `labelQueue(strategy: RECHECK, …)` | re-check: already-labelled frames, never re-checked, served blind (the old label is not sent): first `data/vlm/label_audit.csv` (human disagrees with model OOF and VLM, by priority), then a random sample stratified by the old level. `stats.rechecked/recheckSame/recheckWithinOne` = owner's self-consistency on that random sample only |
| `labelExamples(perClass)` | rubric thumbnails for every scale level: integer-labelled frames whose out-of-fold prediction agrees best with the label (`ml/cache/oof_table.csv`); levels without OOF rows (Nagyon rossz) fall back to the live model score |
| `quickLabel(input: {pointId, rqi, strategy, reason, revealedModel, elapsedMs})` — `rqi` is any level of `shared/rqi_scale.json` (5 = Kiváló … 1 = Nagyon rossz) | upserts `training_data.manual_rqi` (same row shape as `saveTrainingData`; annotations/tags/comment kept); context in `meta_data.quick_label` |
| (re-check save) | overwriting an existing `manual_rqi` appends `{timestamp, old, new, strategy, reason, direction}` to `meta_data.relabel_history` (`direction` = the scale direction the values were written in, so a flip cannot misread them); `manual_rqi` becomes the new value |
| `undoQuickLabel(pointId)` | reverts a quick label: deletes a row it created (if nobody annotated it), else restores the previous `manual_rqi`; never touches review-page labels |

Selection (pure logic, `app/services/label_queue.py`, tested in
`tests/test_label_queue.py`): frames < 50 m from a labelled frame and repeat
panoramas are excluded; no two served frames are < 50 m apart (incl. the
`excludeIds` the client holds). **uncertain** = model score closest to an
ordinal cut-point, round-robin over the Kiváló|Jó, Jó|Közepes, Közepes|Rossz boundaries, near-ties
Budapest first. **diverse** = ≥ 150 m thinning, one frame per 1 km cell per
round (the spatial-CV grid of `ml/spatial_cv.py`), emptiest cell first,
Budapest first, then areas with the fewest labels. **mixed** (default)
interleaves the two. Model outputs (`modelScore`, `modelRqi`, `boundary`) are
converted from the model's severity orientation to the canonical scale direction
(`app.core.rqi_scale`); the model only predicts the scale's `model_levels` (Kiváló … Rossz),
which is why the queue is also how Nagyon rossz labels get collected. Scores: `analysis_metadata.dino_score` when present,
else `data/cache/frame_scores.csv` (`backend/scripts/score_frames.py`, same
v2 artifact, DB untouched).

## REST endpoints (local API only)

None of these is on the public read-only deploy. The frontend uses only the job
stream; the rest have **no caller** in the repo (GraphQL covers them: `points`,
`processRoute`, `job`, `stopJob`) and are kept only for ad-hoc scripting —
candidates for removal.

| Endpoint | Status |
|---|---|
| `GET /api/v1/job/{id}/stream` | **used** — SSE job progress for the React frontend (EventSource cannot do GraphQL) |
| `GET /api/v1/points`, `GET /api/v1/points/{id}` | unused (GraphQL `points` / `point`) |
| `POST /api/v1/process-route` | unused (GraphQL `processRoute`) |
| `GET /api/v1/job/{id}`, `POST /api/v1/job/{id}/stop`, `GET /api/v1/jobs/active` | unused (GraphQL `job`, `stopJob`) |

`/images`, `/previews` and `/api/v1/exports` serve files, not business data.

## Route alternatives (`routeAlternatives`, 2026-11-26)

`routeAlternatives(origin, destination)`: up to 3 driving routes from ONE
Google Directions request (`alternatives=true`, billed like `getRoute`), each
with `distanceM`, `durationS`, `summary`, `points`, its `quality`
(RouteQuality from the stored segments, no extra Google call) and `coverage`.
`fastestIndex`; `smoothestIndex` = lowest speed-weighted impact (below) among routes at
most `ROUTE_SMOOTH_MAX_EXTRA_DURATION` (0.2 = +20 %) slower than the fastest
AND with at least `ROUTE_SMOOTH_MIN_COVERAGE` (0.5) measured; null when none
qualifies. Quality is compared through `app.core.rqi_scale` (direction-free).
Same permission as `getRoute`; on the public schema at most 1 per request.
The planner uses it instead of `getRoute` (which stays for API consumers).

## Removed

`POST /api/v1/inference/detect` is gone: it had no caller, and the GraphQL
`detectObjects` and the product's `performReviewAction` already cover it. There
is no separate REST annotation endpoint.

`GET /api/v1/config` is gone (2026-11-26) and the GraphQL `config` field is
admin-only: both handed the server-side Google Maps key to anonymous callers
(also on the public read-only deploy), and their only consumer, the static
`map.html`, no longer exists.

**Speed-weighted impact (T-47).** `RouteQuality.impactScore` (also inside each
route alternative): the average number of levels below Kiváló per measured
metre, where each metre counts by its speed ÷ 50 km/h — a defect at 90 km/h
weighs 1.8×, at 30 km/h 0.6×; a Kiváló stretch costs 0 at any speed. Lower is
better. Speed = OSM `maxspeed` (stored as `road_segments.maxspeed_kmh`, Alembic
0008, filled by `build_segments.py`), else a default per `highway` class from
`backend/config/route_scoring.json` (editable without a rebuild). Labels stay
surface-only; speed only enters route comparison. `meanScore` is unchanged.

