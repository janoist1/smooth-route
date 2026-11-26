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

## Road-segment layer (`roadSegments`, `routeQuality`)

*Added 2026-11-26. New sections of this file are written in English.*

Quality aggregated on real road geometry: OpenStreetMap ways, stitched into
roads and cut into pieces of about 150 m, each piece summarising the Street
View frames snapped onto it. Both queries are **anonymous**, work on the
read-only deploy (`PUBLIC_READ_ONLY`), and read only the pre-built
`road_segments` table — no Overpass, model or numpy at request time.

```graphql
type RoadSegment {
  id: ID!                   # "<osmWayId>:<pieceIndex>", stable across rebuilds
  path: [[Float!]!]!        # [[lat, lng], ...]
  rqi: Int                  # RQI level, 5 = Kiváló … 2 = Rossz (shared/rqi_scale.json)
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
}
type RouteQuality {
  totalLengthM: Float!
  coveredLengthM: Float!    # metres of the path that run along a segment with data
  lengthByRqi: [Float!]!    # 4 numbers, best first: metres in Kiváló, Jó, Közepes, Rossz
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

**`routeQuality`** — `path` = `[[lat, lng], ...]` (at most 20 000 points). The
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
  Frame P(bad) = `analysis_metadata.dino_p_bad`, else 1/0 for Közepes-or-worse (RQI ≤ 3) / better.
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
