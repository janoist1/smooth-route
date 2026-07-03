# API-felület leltár

*Frissítve: 2026-07-03, C4.*

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
