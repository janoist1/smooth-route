# API-felület leltár

*Frissítve: 2026-11-18 (képkor / `captureDate`).*

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

## Label queue / quick-rate screen (admin-only, 2026-11-26)

Labelling at scale: `labelQueue` picks the unlabelled frames (image on disk,
no `manual_rqi`) whose label helps the model most, and `/training/quick`
("Gyors címkézés") rates them one tap at a time. Own resolver module
(`app/graphql/label_queue.py`), merged into the full schema in `schema.py`; it
is **not** on the public read schema.

| Operation | Purpose |
|---|---|
| `labelQueue(strategy: MIXED\|UNCERTAIN\|DIVERSE, limit, excludeIds)` | next frames + why (`reason`, `area`, `boundary`, `uncertainty`, `cellLabels`) + the model guess (`modelScore/modelRqi/modelPBad`, hidden in the UI until rated) + `stats` |
| `labelExamples(perClass)` | rubric thumbnails for every scale level: integer-labelled frames whose out-of-fold prediction agrees best with the label (`ml/cache/oof_table.csv`); levels without OOF rows (Nagyon rossz) fall back to the live model score |
| `quickLabel(input: {pointId, rqi, strategy, reason, revealedModel, elapsedMs})` — `rqi` is any level of `shared/rqi_scale.json` (1 = Kiváló … 5 = Nagyon rossz today) | upserts `training_data.manual_rqi` (same row shape as `saveTrainingData`; annotations/tags/comment kept); context in `meta_data.quick_label` |
| `undoQuickLabel(pointId)` | reverts a quick label: deletes a row it created (if nobody annotated it), else restores the previous `manual_rqi`; never touches review-page labels |

Selection (pure logic, `app/services/label_queue.py`, tested in
`tests/test_label_queue.py`): frames < 50 m from a labelled frame and repeat
panoramas are excluded; no two served frames are < 50 m apart (incl. the
`excludeIds` the client holds). **uncertain** = model score closest to an
ordinal cut-point, round-robin over the 1|2, 2|3, 3|4 boundaries, near-ties
Budapest first. **diverse** = ≥ 150 m thinning, one frame per 1 km cell per
round (the spatial-CV grid of `ml/spatial_cv.py`), emptiest cell first,
Budapest first, then areas with the fewest labels. **mixed** (default)
interleaves the two. Model outputs (`modelScore`, `modelRqi`, `boundary`) are
converted from the model's severity orientation to the canonical scale direction
(`app.core.rqi_scale`); the model only predicts the scale's `model_levels` (1–4),
which is why the queue is also how Nagyon rossz labels get collected. Scores: `analysis_metadata.dino_score` when present,
else `data/cache/frame_scores.csv` (`backend/scripts/score_frames.py`, same
v2 artifact, DB untouched).



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
