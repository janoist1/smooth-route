# API-felület leltár

*Frissítve: 2026-11-26 (road-segment layer: `roadSegments` / `routeQuality`).*

## Elsődleges termék-API: GraphQL

A Vite/React frontend a `/graphql` felületet használja a pontokhoz,
útvonal-feldolgozáshoz, beállításokhoz, tanításhoz és review-műveletekhez.
Az automatikus YOLO-jelölés a `performReviewAction(action_type:
"auto_detect")` mutáción keresztül fut; a közvetlen `detectObjects` mutáció
megmarad programozott GraphQL-fogyasztóknak.

Read-only RQI-diagnosztika (D3): a `Point` típus a nyers DINO-becslést és a
kalibrált rossz-út valószínűséget is kiadja (`dinoScore`, `dinoPBad`,
az `analysisMetadata`-ból származtatva); a `rqiModelInfo` query az éles
artifact modellkártyáját adja (verzió, recept, tanítóméret, CV-metrikák) a
beállítások felülethez.

Képkor: a `Point.captureDate` (`String`, `"ÉÉÉÉ-HH"`, `null` = ismeretlen) a
Street View-panoráma **készítési hónapja** a Metadata API `date` mezőjéből —
az RQI ennek a hónapnak az útállapotát írja le, nem a `createdAt`-ét (az a mi
letöltésünk ideje). Anonim és a read-only deployon is olvasható (`point`,
`points`, `trainingPoints`). DB-ben `street_view_images.capture_date` (`DATE`,
a hónap 1-je; Alembic `0004`). Új pontoknál a gyűjtés (`route_collector`) és a
letöltés (`image_downloader`) tölti; a meglévőket a
`backend/scripts/backfill_capture_date.py` (rate-limitelt, újrafuttatható,
csak a `NULL`-okat nézi). `pano_id` nélküli pontnál csak akkor ír dátumot, ha
a ma élő panoráma a letöltésünk hónapjánál korábbi — különben a Google azóta
lecserélte a képet, és a dátum nem a mi képünké. A `publish.py` átviszi a
mezőt a Neonba. A frontend 4 évnél régebbi képnél figyelmeztet, és a térképen
opcionálisan halványítja ezeket a pontokat.

## Road-segment layer (`roadSegments`, `routeQuality`, `segmentFrames`)

*Added 2026-11-26. New sections of this file are written in English.*

Quality aggregated on real road geometry: OpenStreetMap ways, stitched into
roads and cut into pieces of about 200 m, each piece summarising the Street
View frames snapped onto it. All of it is **anonymous**, works on the
read-only deploy (`PUBLIC_READ_ONLY`), and reads only the pre-built
`road_segments` table — no Overpass, model or numpy at request time.

```graphql
type RoadSegment {
  id: ID!                   # "<osmWayId>:<pieceIndex>", stable across rebuilds
  path: [[Float!]!]!        # [[lat, lng], ...]
  rqi: Int                  # class label (scale: see "The RQI scale" below)
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
  confidenceReason: String  # "few_images" | "disagreement" | "near_threshold" | "old_images"; null when high
  streetViewUrl: String     # Street View deep link at the piece midpoint
}
type RouteQuality {
  totalLengthM: Float!
  coveredLengthM: Float!    # = sum(lengthByRqi)
  lengthByRqi: [Float!]!    # metres per class, ascending class label (today 1, 2, 3, 4)
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
  has fewer than `min_images` frames; `null` for `confidenceLevel = "high"`.
- `streetViewUrl` — same scheme as `Point.streetViewUrl`
  (`…/maps/@?api=1&map_action=pano&viewpoint=<lat>,<lng>&heading=<h>&pitch=-20`),
  at the middle of the unsimplified piece, heading along the road. Free link,
  no API call. (It is a viewpoint link: Google picks the nearest panorama.)

**`routeQuality`** — `path` = `[[lat, lng], ...]` (at most 20 000 points). The
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

**The RQI scale lives in one place.** Which class labels exist, which way the
scale runs and where "bad" starts are stated only in the config —
`thresholds` plus

```json
"scale": {"classes": [1, 2, 3, 4], "higher_is_worse": true, "bad_class": 3}
```

— and interpreted only by `RqiScale` in `segment_aggregation.py` (`classes` =
labels by ascending score; `bad_class` and everything worse is "bad"). No other
segment code compares a score or class to a literal. Flipping to
"5 = excellent" (data x → 6 − x) is therefore a config edit —
`"thresholds": [2.993, 3.528, 4.423]`,
`"scale": {"classes": [2, 3, 4, 5], "higher_is_worse": false, "bad_class": 3}`
— followed by a full `build_segments.py` run. `lengthByRqi` then lists classes
2, 3, 4, 5 and `worstSegments` puts the lowest scores first. Both keys are
required: a missing or invalid config file is an error, not a silent default.

**Data flow.**

- Table `road_segments` (Alembic `0005`, additive): `id`, `osm_way_id`,
  `piece_index`, `geom` (LineString 4326, GiST), `length_m`, `road_name`,
  `highway`, `n_images`, `score`, `rqi`, `p_bad`, `confidence`,
  `capture_date_min/max`, `updated_at`. Derived data — safe to rebuild. Only
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

## Megtartott REST-végpontok

| Végpont | Indok |
|---|---|
| `GET /api/v1/config` | A beépített statikus térkép Google Maps konfigurációja |
| `GET /api/v1/points`, `GET /api/v1/points/{id}` | A statikus térkép és a README-ben dokumentált egyszerű API |
| `POST /api/v1/process-route` | A statikus térkép útvonal-feldolgozása |
| `GET /api/v1/job/{id}` | A statikus térkép állapotlekérdezése |
| `GET /api/v1/job/{id}/stream` | A React frontend SSE állapotcsatornája |
| `POST /api/v1/job/{id}/stop`, `GET /api/v1/jobs/active` | Job-életciklus és visszacsatlakozás |

A `/images`, `/previews` és `/api/v1/exports` fájlkiszolgáló végpont, nem
üzleti API-duplikáció.

## Kivezetett duplikáció

`POST /api/v1/inference/detect` megszűnt: nem volt hívója, és ugyanazt a
funkciót a GraphQL `detectObjects`, illetve a termékben használt
`performReviewAction` már lefedi. Külön REST annotációs végpont nincs.
