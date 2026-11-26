# AGENTS.md — belépőpont AI-ágenseknek

Ez a fájl bármely AI kódoló ágensnek szól (Claude, GPT, Codex, Cursor, Aider,
stb.). **Vékony útválasztó:** ne olvass be mindent — a lenti táblából nyisd meg
CSAK a feladatodhoz tartozó fájlokat. Így kicsi marad a kontextus és a zaj.

## Mi ez a projekt (egy bekezdés)

Kátyúőr / smooth-route: Google Street View képekről becsüli az út minőségét
(RQI 1–5, ahol **1 = kiváló, 4 = rossz**; az 5-öt nem használjuk). Térképen
mutatja, útvonaltervezéshez. Az **éles RQI-motor** a `ml/` pipeline v2 modellje
(fagyasztott DINOv2-small + SVR-fej + hangolt vágópontok, az
`ml/cache/rqi_model.joblib` artifactban); a backend a `dino_service.py`-n át
tölti, **nyers képen** fut. A YOLO (`road_analyzer.py`) NEM konkurens: az
hibapoligonokat ad a részletkártyához, nem az RQI-t.

## Útválasztó — mit nyiss meg, mit ne

| Ha ezen dolgozol… | Nyisd meg | NE olvasd |
|---|---|---|
| **RQI-modell / `ml/`** | [ml/README.md](ml/README.md), [docs/GLOSSARY.md](docs/GLOSSARY.md) | `frontend/**` |
| **Frontend UI** | [frontend/ARCHITECTURE.md](frontend/ARCHITECTURE.md) | `ml/**` |
| **A javítási terv végrehajtása** | [docs/IMPROVEMENT_PLAN.md](docs/IMPROVEMENT_PLAN.md) — csak a saját fázisod | a többi fázis részletei |
| **Backend API / GraphQL** | [docs/API_SURFACE.md](docs/API_SURFACE.md) | — |
| **Publikálás: auth / queue / kvóták / deploy** | [docs/PUBLISH_PLAN.md](docs/PUBLISH_PLAN.md) — csak a saját fázisod (F0–F6) | a többi fázis részletei |
| **„Miért így van?" / előzmények** | [docs/MODEL_EXPERIMENTS.md](docs/MODEL_EXPERIMENTS.md) | — |
| **Szakszó nem világos** (QWK, MAE, 5-fold CV…) | [docs/GLOSSARY.md](docs/GLOSSARY.md) | — |
| **Címkézési útmutató** | [docs/TrainingGuide.md](docs/TrainingGuide.md) | — |

Elv: **egy fájl = egy felelősség, önhordozó.** Ha egy táblasor fájljaiból
megérted a feladatot, ne nyiss meg többet.

## Futtatás és fejlesztőkörnyezet

- **Python:** MINDIG a `.venv/bin/python` (torch + MPS itt van). Ne hozz létre új
  venv-et. A backend-teszteknek nem kell torch/DB. **Git worktree-ben** nincs saját
  `.venv` — a fő checkout interpreterét használd (abszolút úttal).
- **Node:** 22+ (CI: Node 22). Frontend: React 19 + Vite 8 + Vitest 4.
- **DB:** Postgres/PostGIS Dockerben, **:5433**-on: `docker compose up -d db`.
- **Dev szerver:** `make dev` (backend uvicorn :8000 + Vite frontend :5173).
- **Google Maps kulcs:** a gyökér `.env`-ben (`GOOGLE_MAPS_API_KEY`), route→kép
  letöltéshez kell.

## Tesztek / kapuk (minden PR előtt futtatandó)

```bash
cd backend && ../.venv/bin/python -m pytest -q                 # izolált, nincs DB/torch
cd frontend && npm ci && npm run typecheck && npm run lint && npm test && npm run build
```

CI a pytestet és a frontend typecheck/lint/testet futtatja
(`.github/workflows/ci.yml`); a buildet a Vercel futtatja pushkor, ezért lokálisan
is kell. **Zöld nélkül nem kész.**

### ML-élesítési kapu (KRITIKUS szabály)

Új/módosított RQI-modellt (`ml/cache/rqi_model.joblib`) CSAK akkor élesíts, ha
`.venv/bin/python ml/evaluate_artifact.py` **PASS**-t ad. Ez **térben
csoportosított** 5-fold CV-n mér (1 km-es rácscellák, StratifiedGroupKFold,
seed=42, beágyazott vágópont-hangolás; ld. `ml/spatial_cv.py`), és a bajnokhoz
hasonlít: **QWK ≥ 0.774, MAE ≤ 0.405, bad-AUC ≥ 0.934**. A régi, véletlen-foldos
0.889/0.195/0.970 számok térbeli szivárgás miatt optimisták voltak, ne
hivatkozz rájuk. A „mérhetően jobb" feltétele: a kapu páros összevetésében a
ΔQWK 95%-os CI-je 0 fölött van. A koordináták forrása `ml/image_coords.csv`
(`ml/build_coords.py`); új címkék után ezt is újra kell generálni. Sose az
`ml/legacy/` (v1: `train.py`, `save_model.py`, `extract_features.py`) vagy a
`backend/train_dino_head.py` szkripteket használd, azok referenciák vagy
zsákutcák. Fogalmak: [docs/GLOSSARY.md](docs/GLOSSARY.md).

## Buktatók (amiken más már elvérzett)

- **Kanonikus adatkönyvtár:** a backend és az ML-pipeline egyaránt a gyökér
  `data/` könyvtárat használja (relatív `DATA_DIR` is a repó gyökeréhez oldódik).
  Ne hozz létre újra `backend/data/` fát.
- **A modell nyers képen fut:** ne told bele az előfeldolgozást (FastSAM/CLAHE
  stb.) az RQI-útba — a tanítás is nyers képen ment.
- **Egy review-felület, két panel:** a címkézés `/training/:id/review`-n megy
  (pontozás + poligonjelölés); nincs külön `/training/dino` útvonal, és a régi
  DINO-*tanítás* gomb megszűnt. Az RQI-modellt az `ml/` pipeline tanítja, nem a web.
  Gyors, mobilos RQI-címkézés: `/training/quick` (label queue, ld.
  [docs/API_SURFACE.md](docs/API_SURFACE.md)); ugyanabba a `training_data`-ba ír.
- **Két backend-függőséglista:** `backend/pyproject.toml` (teljes, torch-csal) és
  `backend/requirements.txt` (torch-mentes, CSAK a Vercel-deployhoz; a
  `.vercelignore` rejti el a pyproject-et). Új futásidejű függőség a read-only
  útvonalon mindkettőbe kell.
- **SQLAlchemy `<2.1`:** a 2.1 a sima `postgresql://` URL-t psycopg v3-ra képezi
  (psycopg2 helyett) → CI és Vercel elhasal. A plafon csak driverváltással együtt
  emelhető.
- **A CLI nagy része törött:** `collect-points`, `download-images`,
  `fetch-missing-images`, `analyze-points` a már nem létező `processing_service`-t
  importálja; a webes job-flow a működő út.
- **Gyökér rendben tartása:** egyszeri szkript → `scripts/` (ha a `Makefile`
  használja) vagy `scripts/legacy/`; elavult jegyzet → `docs/archive/`.

## Állapot (2026-11-18)

A javítási terv **A–D fázisa kész**. A publikálás **kétkörös**
(ld. [docs/PUBLISH_PLAN.md](docs/PUBLISH_PLAN.md)): az elemzés lokálisan, kérésre
fut, így **round 1 = read-only publikálás**. Deploy-topológia: **két Vercel-
projekt** (frontend + `backend/` `PUBLIC_READ_ONLY=1`-gyel), **Neon** olvasható DB,
a képek helyett Google Street View deep-linkek; mindkettő a `master` pusholásakor
deployol. Kész: **F1** (Clerk auth), **F1.5** (minőség-rács + admin stats),
**R1.1** (pano_id + SV link), **R1.2** (read-only mód + Vercel-artefaktumok),
**R1.3** (`backend/scripts/publish.py` → Neon); az oldal a Vercel alap-domainjein
él. **Nyitott: R1.4** (DNS `simaut.hu` / `api.simaut.hu`, Google-kulcs
restrikció, budget-alert). A round-2 (auth/queue/kvóta, F0–F6) a user-beküldésig
vár. 2026-11: repó-takarítás (legacy szkriptek/jegyzetek áthelyezve),
függőségfrissítés (frontend: Vite 8, Vitest 4, graphql-codegen 8, lucide 1.x;
backend: CVE-floorok, Pydantic/SQLAlchemy/utcnow elavulások). A lokális dev
változatlan (`make dev`, teljes backend); a read-only csak env-flag.
Commit/push csak explicit kérésre.

**RQI-kiértékelés (2026-11-18):** térben csoportosított CV-re váltottunk. A v2
bajnok őszinte számai: QWK 0.774 / MAE 0.405 / AUC 0.934. Budapesten gyenge,
új régióban QWK ~0.66. A bajnok marad, mert egyik kihívó sem mérhetően jobb.
Teendők (holdout régió, szórtabb címkék, szakasz-aggregálás):
[docs/MODEL_EXPERIMENTS.md](docs/MODEL_EXPERIMENTS.md), 6. korszak.
**Képdátum (2026-11-18):** `street_view_images.capture_date` (Metadata API,
ingyenes) + `backend/scripts/backfill_capture_date.py`; a részletkártya jelzi a
régi képet.
