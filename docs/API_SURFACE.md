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

## Megtartott REST-végpontok

| Végpont | Indok |
|---|---|
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

`GET /api/v1/config` megszűnt (2026-11-26), a GraphQL `config` pedig csak
adminnak érhető el: mindkettő anonim módon kiadta a szerveroldali Google
Maps-kulcsot (a read-only éles deployon is), a fogyasztójuk, a statikus
`map.html` pedig már nem létezik.
