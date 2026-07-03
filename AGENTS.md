# AGENTS.md — belépőpont AI-ágenseknek

Ez a fájl bármely AI kódoló ágensnek szól (Claude, GPT, Codex, Cursor, Aider,
stb.). Olvasd el **mielőtt** bármihez hozzányúlsz. Cél: a
[docs/IMPROVEMENT_PLAN.md](docs/IMPROVEMENT_PLAN.md) végrehajtható legyen anélkül,
hogy láttad volna a keletkezését.

## Mi ez a projekt

Kátyúőr / smooth-route: Google Street View képekről becsli az út minőségét
(RQI 1–5, ahol **1 = kiváló, 4 = rossz**; az 5 gyakorlatilag nincs). Térképen
mutatja, útvonaltervezéshez.

**Az éles RQI-motor** a `ml/` pipeline v2 modellje: fagyasztott DINOv2-small
(CLS + patch-token átlag) + SVR-RBF fej + hangolt ordinális vágópontok, a
`ml/cache/rqi_model.joblib` artifactban. A backend a
`backend/app/services/dino_service.py`-n át tölti; **nyers képen** fut (nincs
előfeldolgozás). A YOLO (`road_analyzer.py`) NEM konkurens: az hibapoligonokat
ad a részletkártyához, nem az RQI-t.

## KÖTELEZŐ olvasmány a terv előtt

1. [docs/IMPROVEMENT_PLAN.md](docs/IMPROVEMENT_PLAN.md) — a végrehajtandó terv
   (fázisok A–E, függések, elfogadási kritériumok). **Ez a munkalista.**
2. [docs/MODEL_EXPERIMENTS.md](docs/MODEL_EXPERIMENTS.md) — miért így néz ki a
   rendszer; mi élő és mi zsákutca. Olvasd el, mielőtt bármit "modellként"
   kezelnél.
3. [ml/README.md](ml/README.md) — az ML-pipeline receptje és számai.
4. [frontend/ARCHITECTURE.md](frontend/ARCHITECTURE.md) — modulhatár-szabályok
   (ESLint kényszeríti; components nem importálhat slice/sagas/selectors-t
   közvetlenül).

## Futtatás és fejlesztőkörnyezet

- **Python:** MINDIG a `.venv/bin/python`-t használd (torch + MPS itt van).
  Ne hozz létre új venv-et. A backend-teszteknek nem kell torch/DB.
- **DB:** Postgres/PostGIS Dockerben, **:5433**-on: `docker compose up -d db`.
- **Dev szerver:** `make dev` (backend uvicorn :8000 + Vite frontend :5173).
- **Google Maps kulcs:** a gyökér `.env`-ben (`GOOGLE_MAPS_API_KEY`), route→kép
  letöltéshez kell. A README részben elavult — a mérvadó a `make dev` és ez a fájl.

## Tesztek / kapuk (minden PR előtt futtatandó)

```bash
# Backend (izolált, nincs DB/torch):
cd backend && ../.venv/bin/python -m pytest -q
# Frontend:
cd frontend && npm run typecheck && npm run lint && npm test
```

CI mindkettőt futtatja (`.github/workflows/ci.yml`). **Zöld nélkül nem kész.**

### ML-élesítési kapu (KRITIKUS szabály)

Új/módosított RQI-modellt CSAK akkor élesíts (`ml/cache/rqi_model.joblib`), ha
az `ml/experiments.py` / `ml/tune_svr.py` **5-fold CV**-jén (fix seed=42, azonos
fold-ok) **veri vagy hozza** a jelenlegit: **QWK 0.889, MAE 0.195, bad-AUC 0.970**.
Sose a régi `ml/train.py` vagy `backend/train_dino_head.py` szkripteket
használd — azok referencia/zsákutca (ld. MODEL_EXPERIMENTS.md).

## Buktatók (amiken más már elvérzett)

- **Kanonikus adatkönyvtár:** a backend és az ML-pipeline egyaránt a gyökér
  `data/` könyvtárat használja; relatív `DATA_DIR` felülírás is a repó
  gyökeréhez képest oldódik fel. Ne hozz létre újra `backend/data/` fát.
- **Háromféle "dino" webes felület, KÜLÖN sorssal** (ld. terv P1/P9):
  (1) DINO *tanítás* gomb = halott, törlendő; (2) DINO *review/pontozó* nézet =
  élő, kell (ez adja a `manual_rqi` címkéket); (3) a `/dino` URL = megszüntetendő.
  Ne töröld a review-t a tanítással együtt.
- **Lappangó bug:** `google_maps.py` `Optional`-t használ import nélkül
  (Python 3.14 maszkolja) — az A1 lépés javítja.
- **Régi settings-szemét:** a `backend/config/analysis_settings.json`-ban halott
  heurisztika-kulcsok vannak (ld. terv P2/B2).

## Git-állapot (fontos a kezdéskor)

A terv és az ML-munka egy része lehet **commitolatlan** (`git status`). Kezdés
előtt tisztázd az emberrel a kiindulási commitot, vagy dolgozz külön ágon.
Commit/push csak explicit kérésre.
