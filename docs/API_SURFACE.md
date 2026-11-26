# API surface inventory

*Updated: 2026-11-26 (`/api/v1/config` removed; previously 2026-11-18, image age / `captureDate`).*

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
