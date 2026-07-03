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
  venv-et. A backend-teszteknek nem kell torch/DB.
- **DB:** Postgres/PostGIS Dockerben, **:5433**-on: `docker compose up -d db`.
- **Dev szerver:** `make dev` (backend uvicorn :8000 + Vite frontend :5173).
- **Google Maps kulcs:** a gyökér `.env`-ben (`GOOGLE_MAPS_API_KEY`), route→kép
  letöltéshez kell.

## Tesztek / kapuk (minden PR előtt futtatandó)

```bash
cd backend && ../.venv/bin/python -m pytest -q                 # izolált, nincs DB/torch
cd frontend && npm run typecheck && npm run lint && npm test
```

CI mindkettőt futtatja (`.github/workflows/ci.yml`). **Zöld nélkül nem kész.**

### ML-élesítési kapu (KRITIKUS szabály)

Új/módosított RQI-modellt (`ml/cache/rqi_model.joblib`) CSAK akkor élesíts, ha
`.venv/bin/python ml/evaluate_artifact.py` **PASS**-t ad — ez a rögzített 5-fold
CV-n (seed=42) újramér és a bajnokhoz méri (**QWK ≥ 0.889, MAE ≤ 0.195,
bad-AUC ≥ 0.970**). Sose a régi `ml/train.py` / `backend/train_dino_head.py`
szkripteket használd — azok referencia/zsákutca. Fogalmak: [docs/GLOSSARY.md](docs/GLOSSARY.md).

## Buktatók (amiken más már elvérzett)

- **Kanonikus adatkönyvtár:** a backend és az ML-pipeline egyaránt a gyökér
  `data/` könyvtárat használja (relatív `DATA_DIR` is a repó gyökeréhez oldódik).
  Ne hozz létre újra `backend/data/` fát.
- **A modell nyers képen fut:** ne told bele az előfeldolgozást (FastSAM/CLAHE
  stb.) az RQI-útba — a tanítás is nyers képen ment.
- **Egy review-felület, két panel:** a címkézés `/training/:id/review`-n megy
  (pontozás + poligonjelölés); nincs külön `/training/dino` útvonal, és a régi
  DINO-*tanítás* gomb megszűnt. Az RQI-modellt az `ml/` pipeline tanítja, nem a web.

## Állapot (2026-07-03)

A javítási terv **A–D fázisa kész**. A publikálás **átteljezve kétkörösre**
(ld. [docs/PUBLISH_PLAN.md](docs/PUBLISH_PLAN.md)): az elemzés lokálisan, kérésre
fut, így **round 1 = read-only publikálás** (Vercel + Neon + Street View
deep-linkek). Kész és commitolva: **F1** (Clerk auth), **F1.5** (térkép
minőség-rács + admin stats/monitoring oldal), az **F0 Alembic-része**, plusz
SSE-progress és pont-limit fixek. **Soron következő: Round 1 (R1.1–R1.5)** —
pano_id + Street View link, torch-mentes read-backend Vercelre, Neon +
publish-script, deploy `simaut.hu`-ra. A round-2 (auth/queue/kvóta, F0–F6) a
user-beküldésig vár. Commit/push csak explicit kérésre.
