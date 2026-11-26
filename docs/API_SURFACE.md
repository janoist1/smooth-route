# API surface inventory

*Updated 2026-11-26.* GraphQL (`/graphql`) is the product API; REST is only
the job stream. The tables below are checked against the schema objects by
`backend/scripts/check_api_docs.py` (fields, access, read-only flag, and
`schema.graphql` freshness) — change a resolver, then update its row.

## Two schemas, three access levels

`app/graphql/schema.py` builds two schemas from the same resolvers:

- **Full schema** — local dev / the always-on backend: every row below.
- **Read-only schema** — the public deploy (`PUBLIC_READ_ONLY=1`): the
  "RO" = yes rows only. No mutations, no label-queue / pairwise / model-panel
  fields. Introspection off, unexpected errors masked, POST only.

Access (`app/graphql/permissions.py`):

| Access | Meaning |
|---|---|
| `anonymous` | no permission class |
| `signed-in` | `IsAuthenticated` — any identity |
| `signed-in*` | `IsAuthenticatedUnlessPublicRead` — signed in on the full backend, anonymous on the read-only deploy |
| `admin` | `IsAdmin`. Admin rows with RO = yes are on the read-only schema but still answer `FORBIDDEN` without an admin identity |

Request limits (`app/graphql/limits.py`, both schemas): depth ≤ 8, aliases
≤ 10, ≤ 2000 tokens; per operation at most 1 paid route field (`getRoute` or
`routeAlternatives`), 1 `routeQuality`, 2 each of `points`, `roadQualityGrid`,
`roadSegments`, `segmentFrames`; `Point.segmentId` only under `point`. Route
endpoints given as coordinates must lie in the service area (Hungary + margin).
Violations are `BAD_USER_INPUT` errors raised before any resolver runs.

## Queries

| Field | Access | RO | Purpose |
|---|---|---|---|
| `me` | anonymous | yes | caller identity (`clerkId`, `email`, `role`); `null` when not signed in |
| `point` | anonymous | yes | one frame by id |
| `points` | anonymous | yes | frames for the map; `bbox` + `limit` ≤ 20 000, without `bbox` ≤ 1 000 |
| `roadQualityGrid` | anonymous | yes | zoomed-out overview: average RQI per grid cell, JSON `{cell, cells: [[swLat, swLng, avgRqi]]}` |
| `roadSegments` | anonymous | yes | road segments with quality in a viewport ([segment layer](#road-segment-layer)) |
| `routeQuality` | anonymous | yes | quality summary of a path from the stored segments |
| `segmentFrames` | anonymous | yes | the frames a segment was aggregated from |
| `getRoute` | signed-in* | yes | one driving route (one paid Google Directions call); kept for API consumers |
| `routeAlternatives` | signed-in* | yes | up to 3 routes with quality, fastest / smoothest ([routes](#routes)) |
| `job` | anonymous | yes | job status by id |
| `activeJob` | anonymous | yes | the running job, if any |
| `config` | admin | no | server-side Google Maps key; on the read-only schema the guard rejects it for everyone |
| `settings` | admin | yes | all settings rows |
| `availableModels` | admin | yes | YOLO weight files in `data/models` |
| `rqiModelInfo` | admin | yes | model card of the live RQI artifact ([model](#rqi-model-admin)) |
| `adminStats` | admin | yes | usage / coverage / job stats for the admin page |
| `trainingPoints` | admin | yes | paged frames for the review screen, by `FilterMode` |
| `trainingStats` | admin | yes | label counts for the review screen |
| `nextTrainingPoint` | admin | yes | id of the next frame in review order |
| `labelQueue` | admin | no | next frames to label, by strategy ([labelling](#labelling-admin)) |
| `labelExamples` | admin | no | rubric thumbnails per scale level |
| `pairQueue` | admin | no | frame pairs for pairwise judgment |
| `modelAdmin` | admin | no | unseen labels, sprint progress, latest retrain report |

## Mutations (full schema only)

| Field | Access | RO | Purpose |
|---|---|---|---|
| `processRoute` | signed-in | no | start a route collection + analysis job |
| `stopJob` | signed-in | no | cancel a job |
| `updateSetting` | admin | no | change one setting |
| `applyPreset` | admin | no | change several settings at once |
| `runAnalysis` | admin | no | start an analysis job over stored frames |
| `startModelTraining` | admin | no | start a YOLO training job (not the RQI model) |
| `saveTrainingData` | admin | no | save a review-screen label (RQI, tags, polygons, comment) |
| `deleteTrainingData` | admin | no | delete a frame's label |
| `performReviewAction` | admin | no | review-screen actions, incl. automatic YOLO marking (`action_type: "auto_detect"`) |
| `detectObjects` | admin | no | raw YOLO detection on one image, for API consumers |
| `predictDinoRqi` | admin | no | RQI class of one image from the live model |
| `quickLabel` | admin | no | save a quick-rate label |
| `undoQuickLabel` | admin | no | revert a quick-rate label |
| `submitPairJudgment` | admin | no | store one pairwise judgment |
| `undoPairJudgment` | admin | no | delete a pairwise judgment by `clientId` |
| `startRetrain` | admin | no | start `ml/retrain.py` as a job |
| `promoteCandidate` | admin | no | make the retrained candidate the live model |
| `startRescoreAndRebuild` | admin | no | re-score stored frames, then rebuild the segments |

## `Point`

`rqiScore` is the product RQI and `rqiSource` says where it came from;
`dinoScore` / `dinoPBad` are the raw model estimate and the calibrated
bad-road probability (from `analysisMetadata`). The labeller fields
(`manualRqi`, `manualTags`, `manualAnnotations`, `manualComment`) are plain
fields, readable wherever `point` / `points` are.

`captureDate` (`"YYYY-MM"`, `null` = unknown) is the Street View panorama's
**capture month** — the RQI describes the road as of that month, not as of
`createdAt` (our download time). Stored as `street_view_images.capture_date`
(`DATE`, 1st of the month; Alembic `0004`); filled at collection and download,
and for older rows by `backend/scripts/backfill_capture_date.py`
(rate-limited, re-runnable, only `NULL`s; without a `pano_id` it writes a date
only when the panorama live today predates our download month). `publish.py`
carries it to Neon. The frontend warns for images older than 4 years.

<a id="road-segment-layer"></a>
## Road-segment layer (`roadSegments`, `routeQuality`, `segmentFrames`)

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
  impactScore: Float        # speed-weighted impact, lower is better (see Routes)
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
`ST_Simplify` (Douglas-Peucker, collapsed pieces kept) at half a screen pixel for the zoom, unsimplified
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
800 km, `limits.py`). The path is sampled every 10 m; a sample belongs to the nearest segment within
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

<a id="routes"></a>
## Routes (`getRoute`, `routeAlternatives`)

`routeAlternatives(origin, destination)`: up to 3 driving routes from ONE
Google Directions request (`alternatives=true`, billed like `getRoute`), each
with `distanceM`, `durationS`, `summary`, `points`, its `quality`
(`RouteQuality` from the stored segments, no extra Google call) and `coverage`.
`fastestIndex`; `smoothestIndex` = lowest speed-weighted impact among routes at
most `ROUTE_SMOOTH_MAX_EXTRA_DURATION` (0.2 = +20 %) slower than the fastest
AND with at least `ROUTE_SMOOTH_MIN_COVERAGE` (0.5) measured; `null` when none
qualifies. Quality is compared through `app.core.rqi_scale` (direction-free).
The planner uses it instead of `getRoute`.

**Speed-weighted impact (T-47).** `RouteQuality.impactScore` (also inside each
route alternative): the average number of levels below Kiváló per measured
metre, where each metre counts by its speed ÷ 50 km/h — a defect at 90 km/h
weighs 1.8×, at 30 km/h 0.6×; a Kiváló stretch costs 0 at any speed. Lower is
better. Speed = OSM `maxspeed` (stored as `road_segments.maxspeed_kmh`, Alembic
0008, filled by `build_segments.py`), else a default per `highway` class from
`backend/config/route_scoring.json` (editable without a rebuild). Labels stay
surface-only; speed only enters route comparison. `meanScore` is unchanged.

<a id="labelling-admin"></a>
## Labelling (admin, full schema only)

Resolvers in `app/graphql/label_queue.py`, selection logic in
`app/services/label_queue.py` (`tests/test_label_queue.py`). The quick-rate
screen is `/training/quick`; the model guess is hidden until a frame is rated.

| `labelQueue` strategy | Serves |
|---|---|
| `MIXED` (default) | `UNCERTAIN` and `DIVERSE` interleaved |
| `UNCERTAIN` | model score closest to a class cut-point, round-robin over the three boundaries, Budapest first on near-ties |
| `DIVERSE` | ≥ 150 m thinning, one frame per 1 km cell per round (grid of `ml/spatial_cv.py`), emptiest cell first |
| `SPRINT` | learning-curve sprint on new streets: emptiest 1 km cells, Budapest first, ≤ 1 frame per 75 m, every 4th from the frames the model rates best |
| `RECHECK` | already-labelled frames served blind: first `data/vlm/label_audit.csv` (human vs model OOF and VLM disagreement), then a random sample stratified by the old level |

Each item carries why it was picked (`reason`, `area`, `boundary`,
`uncertainty`, `cellLabels`) and the model guess (`modelScore`, `modelRqi`,
`modelPBad`). `stats` adds `sprintLabelled / sprintTarget` (progress bar; the
page suggests `make retrain` after every 200) and
`rechecked / recheckSame / recheckWithinOne` (the owner's self-consistency on
the random re-check sample).

- Unlabelled strategies serve frames with an image on disk and no
  `manual_rqi`; frames < 50 m from a labelled frame and repeat panoramas are
  excluded, and no two served frames are < 50 m apart (incl. `excludeIds`).
- Model outputs are converted from the model's severity orientation to the
  canonical scale (`app.core.rqi_scale`). The model only predicts the scale's
  `model_levels` (Kiváló … Rossz), so the queue is also how Nagyon rossz labels
  get collected. Scores: `analysis_metadata.dino_score`, else
  `data/cache/frame_scores.csv` (`backend/scripts/score_frames.py`).
- `labelExamples(perClass)`: integer-labelled frames whose out-of-fold
  prediction agrees best with the label (`ml/cache/oof_table.csv`); levels
  without OOF rows fall back to the live model score.
- `quickLabel(input: {pointId, rqi, strategy, reason, revealedModel,
  elapsedMs})` — `rqi` is any level of `shared/rqi_scale.json`. Upserts
  `training_data.manual_rqi` (same row as `saveTrainingData`; annotations, tags
  and comment kept), context in `meta_data.quick_label`. Overwriting an existing
  label appends `{timestamp, old, new, strategy, reason, direction}` to
  `meta_data.relabel_history`.
- `undoQuickLabel(pointId)`: deletes a row it created (if nobody annotated
  it), else restores the previous `manual_rqi`; never touches review-page labels.
- **Pairwise:** `pairQueue(limit, excludeIds)` → pairs the model scores within
  0.25 levels, ≥ 500 m apart, never judged before. `submitPairJudgment(input:
  {clientId, frameAId, frameBId, result: A|B|EQUAL, elapsedMs})` stores one row
  in `pair_judgments` (Alembic `0009`; retry-safe by `clientId`).
  `ml/pairwise_scores.py` fits Bradley–Terry scores from them
  (`ml/cache/pairwise_scores.csv`, experiments only).

<a id="rqi-model-admin"></a>
## RQI model (admin)

- `rqiModelInfo` — model card of the live artifact: `version`, `backbone`,
  `recipe`, `head`, `nTrain`, CV metrics (`qwk`, `mae`, `exactAcc`,
  `badRoadAcc`, `badRoadAuc`), where they come from (`metricsSource`,
  `metricsProtocol`, `metricsMeasuredOn`), segment-level and new-area numbers
  (`segmentQwk`, `segmentLengthM`, `newAreaQwk`), `scaleMeaning`;
  `available = false` when no artifact is loaded.
- `modelAdmin` (`app/graphql/model_admin.py`, logic in
  `app/services/model_ops.py`) — labels the champion has not seen (not in
  `ml/cache/dataset_v2.csv`) by area and level, sprint progress, the
  learning-curve hint, and the latest retrain report in plain Hungarian (from
  `ml/cache/retrain/<run>/summary.json`).
- `startRetrain` → job id; runs `ml/retrain.py` (= `make retrain`), progress
  over the SSE job stream. Never promotes.
- `promoteCandidate(confirm: "ÉLESÍTÉS")` — only with the exact phrase, an
  existing candidate and a PASS gate; keeps
  `ml/cache/rqi_model.<UTC>.bak.joblib`, swaps atomically, reloads the live
  model, refreshes `ml/model_card.json` as a job.
- `startRescoreAndRebuild` → job id; `rescore_dino.py`, then
  `build_segments.py --offline` (offered after a promotion).

One model job at a time.

## REST (full backend only)

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/job/{id}/stream` | SSE job progress for the frontend (EventSource cannot do GraphQL) |

`tests/test_api_surface.py` pins the router to this one route. `/images`,
`/previews` and `/api/v1/exports` serve files, not business data. The
read-only deploy serves `/graphql` alone.

## Removed

- REST `GET /api/v1/points`, `GET /api/v1/points/{id}`,
  `POST /api/v1/process-route`, `GET /api/v1/job/{id}`,
  `POST /api/v1/job/{id}/stop`, `GET /api/v1/jobs/active` (2026-11-26, T-65) —
  no caller; the GraphQL fields of the same names cover them.
- REST `POST /api/v1/inference/detect` — covered by `detectObjects` /
  `performReviewAction`.
- REST `GET /api/v1/config` (2026-11-26) — handed the server-side Google Maps
  key to anonymous callers; the GraphQL `config` field became admin-only for
  the same reason.
