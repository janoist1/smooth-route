# Architektúra-átvilágítás és javítási terv

*Készült: 2026-07-03. Cél: a kódbázis legyen jövőálló a további AI-fejlesztésekhez;
az örökölt modell-próbálkozások kerüljenek rendbe; egyértelmű legyen, mi az éles
motor. A kísérletek történetét a [MODEL_EXPERIMENTS.md](MODEL_EXPERIMENTS.md) írja le.*

---

## 1. Átvilágítás — mit találtam

### Ami jó (megtartandó alapok)

- **Tiszta rétegzés a backendben:** `road_quality.py` vékony homlokzat a
  fókuszált egységek felett (`route_collector`, `image_downloader`,
  `road_analyzer`, `rqi_scoring`, `dino_service`); a GraphQL séma
  kompozíciós gyökér, a resolverek különválasztva.
- **A v2 RQI-motor recept-vezérelt:** az artifact (`ml/cache/rqi_model.joblib`)
  géppel olvasható `feature_recipe`-et, hangolt vágópontokat és P(rossz)
  kalibrátort hordoz — modellcsere kódmódosítás nélkül lehetséges.
- **Reprodukálható ML-pipeline** (`ml/`): export → visszatöltés → jellemzők →
  kísérleti rács → hangolás → artifact, fix seed-ű keresztvalidációval.
- **Védőháló:** frontend Vitest + typecheck + ESLint modulhatár-szabályok;
  backend pytest (torch/DB nélkül futó tesztek); CI mindkettőre.

### Fő problémák (súlyossági sorrendben)

| # | Probléma | Hol | Kockázat |
|---|---|---|---|
| P1 | **Zsákutca-*tanítási* út elérhető a webről:** a DINO **tanítás** gomb a régi, hibás receptű `train_dino_head.py`-t futtatja, és olyan `.pt`-t ment, amit **már semmi nem tölt be** (az éles motor a joblib artifactot használja). FIGYELEM: ez a DINO *tanítás* felület, NEM a DINO *review/pontozó* felület (ld. P9) — utóbbi él és kell | `DinoTrainingDashboardPage.tsx` "tanítás indítása" → `startModelTraining("DINO")` → `training_service.py` → `training/local_provider._run_dino_training` → `backend/train_dino_head.py` | A felhasználó "tanít", eredmény nélkül; jövőbeli fejlesztő rossz kódból indul ki |
| P9 | **A review/címkéző felület a modellt szivárogtatja, nem a feladatot:** két párhuzamos útvonal — `/training/:id/review` (hibapoligon-rajzolás, YOLO) és `/training/dino/:id/review` (1–5 RQI-pontozás) — a `/dino` a modellnevet viszi a URL-be. A térkép "Train/Correct" gombja a `rqi_display_source` beállítás alapján csendben más címkéző nézetre irányít. Ráadás: a DINO review-n ott a "Smart ROI (FastSAM)" + kísérleti előfeldolgozó kapcsolók, de az éles RQI-modell **nyers képen** fut → félrevezető | `routes.ts`, `HomePage.tsx:17`, `DinoTrainingView.tsx` (preproc. kapcsolók) | Megerősíti a "két konkurens modell" téves mentális modellt; félrevezető UI |
| P2 | **Halott heurisztika-beállítások:** 9 setting (súlyok + RQI-küszöbök) egy már nem létező stratégiához; a `strategy="HEURISTIC"` alapérték valójában YOLO-t futtat; a GraphQL típuskomment "YOLO, HEURISTIC, FUSION"-t ígér | `backend/config/analysis_settings.json`, `road_quality.py:49`, `graphql/types.py:96` | Félrevezető settings-UI; senki nem tudja, mi él |
| P3 | **Duplikált YOLO-stack:** két külön betöltő/következtető út — `inference.py` (annotáláshoz/review-hoz, 272 sor) és `road_analyzer.py` (útvonal-elemzéshez) — eltérő fallback-modellekkel (`yolov12s-seg.pt` vs `yolov8m-seg.pt`) és `os.getcwd()`-függő útvonal-feloldással; az `inference.py`-ban AI-beszélgetés-törmelék kommentek (220–222. sor) | `backend/app/services/inference.py`, `road_analyzer.py` | Kétszer kell mindent javítani; cwd-től függően más modell töltődhet |
| P4 | **Kettéhasadt adatkönyvtár:** a backend a `backend/data/`-t preferálja (530 MB kép), a tanítóképek a gyökér `data/`-ban (144 MB); modellek 3 helyen (`backend/data/models` 422 MB, `data/models`, backend-gyökér `.pt`-k); +262 MB exports, +224 MB runs törmelék | `config.resolve_data_dir()` | Adatvesztés-közeli helyzet volt: a 676 kép "eltűnése" részben ebből fakadt |
| P5 | **Backend-gyökér törmelék:** debug szkriptek (`check_*`, `debug_*`, `inspect_values`, `reset_jobs`, `verify_preprocessing`, `migrate_dino`), tesztek a `tests/`-en kívül (`test_dino_inference.py`, `test_graphql_point.py`), üres `smooth_route.db`, debug JPG-k, két `debug_preprocessed/` mappa, 31 MB `.pt` a gyökérben | `backend/` gyökér | Zaj; az új fejlesztő (vagy AI-asszisztens) nem tudja, mi számít |
| P6 | **Lappangó bug:** a `google_maps.py` `Optional`-t használ import nélkül — a Python 3.14 lusta annotáció-kiértékelése (PEP 649) maszkolja, de bármilyen introspekció (pl. jövőbeli séma-generálás) `NameError`-rel elszáll | `backend/app/services/google_maps.py:123,156,237` | Időzített bomba |
| P7 | **FastSAM félholt:** a `preprocessing.py` (+24 MB FastSAM-s.pt) csak a YOLO-tanítóadat-exportban és az annotáló-előnézetben fut; az RQI-út nyers képeken megy | `preprocessing.py`, `training_service.py:265`, `review_service.py` | Karbantartási teher, döntés kell: kell-e még |
| P8 | Kettős API-felület: REST (`api/routes.py`, 348 sor) és GraphQL részben átfedő végpontokkal (pl. detect) | `backend/app/api/routes.py` | Két helyen kell változtatni |

---

## 2. Döntés: egy fix modell vs. választható modellek

**Javaslat: EGY fix RQI-motor (a v2), és NEM építünk webes modellválasztót.**

Indoklás:
- A "modellek" nem egymás alternatívái: a v2 DINO-motor a *"mennyire rossz az
  út?"* kérdésre válaszol (ez az RQI), a YOLO a *"mi a baj vele?"* kérdésre
  (hibapoligonok a részletkártyán). Mindkettő marad, de más-más szerepben.
- Az egyetlen valódi alternatíva (a régi DINO-fej) mérhetően és dokumentáltan
  rosszabb — nincs mit választani rajta.
- A megjelenítési választás **már létezik és elég**: az
  `rqi_display_source` beállítás (yolo / dino / both) a Settings-oldalon
  eldönti, melyik pontszám látszik a térképen. Ez marad.
- Webes modellválasztó = minden jövőbeli modellnél UI + API + migrációs teher,
  miközben a modellcserét az artifact-formátum már kódmódosítás nélkül tudja.
- Amit ehelyett adunk (B4): a Settings-oldalon egy **csak-olvasható
  "modellkártya"** — az éles artifact verziója, tanítóadat-mérete, CV-metrikái.
  Így látható, "mi fut", választási teher nélkül.

---

## 3. A terv — fázisokban

*Jelölés: [S] < fél nap, [M] ~1 nap, [L] több nap. Minden fázis végén: teljes
teszt-suite + egy kézi útvonal-feldolgozás füstteszt.*

### A fázis — Gyors takarítás (kockázatmentes) — összesen ~1 nap

- **A1 [S]** `Optional`-import pótlása a `google_maps.py`-ban (P6) + gyors
  smoke-teszt, hogy más fájlban nincs hasonló (pl. `ruff check` bekapcsolása
  F821-re a backend CI-ban — ez automatikusan fogja a jövőben).
- **A2 [S]** Backend-gyökér törmelék (P5): `debug_*`, `check_*`,
  `inspect_values.py`, `reset_jobs.py`, `verify_preprocessing.py`,
  `migrate_dino.py`, üres `smooth_route.db`, `debug_error.log`, debug JPG-k,
  `debug_preprocessed/` törlése; `test_dino_inference.py` és
  `test_graphql_point.py` vagy a `tests/`-be integrálva, vagy törölve.
  A hasznosnak ítélt egyszeri szkriptek a `scripts/`-be, docstringgel.
- **A3 [S]** Nagy bináris/futás-törmelék: `backend/data/runs` (224 MB),
  `backend/data/exports` (262 MB) áttekintése → ami kell, archív mappába,
  a többi törlés; `.gitignore` ellenőrzése ezekre a mintákra.

### B fázis — Zsákutcák lezárása + webes felületek egységesítése — ~3 nap

> **A háromféle "dino" webes felület, külön sorssal** (fontos, mert könnyű
> összekeverni):
> 1. DINO **tanítás** (dashboard "tanítás indítása" gomb) → **halott, törlendő** (B1).
> 2. DINO **review/pontozó** nézet (1–5 gombok, a felhasználó képe) → **él és
>    kell**, ez adja a `manual_rqi` címkéket → **megtartani, de a YOLO-review-val
>    egy feladat-alapú nézetbe vonni** (B4).
> 3. A `/dino` **URL-szeparáció** → megszűnik a B4-ben.

- **B1 [M]** **Régi DINO-*tanítóút* kivezetése** (P1) — csak a *tanítás*, a
  *review* marad:
  - törlés: `backend/train_dino_head.py`, `local_provider._run_dino_training`,
    `training_service.export_dino_data` + a `model_type="DINO"` ágak,
    `data/models/dino_rqi_head_vits14.pt`, `backend/data/dino_dataset`;
  - frontend: a `DinoTrainingDashboardPage` "tanítás indítása" akciójának
    eltávolítása; helyén rövid magyarázó blokk: az RQI-modell tanítása az `ml/`
    pipeline-ban történik (link a `ml/README.md`-re és a MODEL_EXPERIMENTS.md-re);
  - a `dino_model_name`, `dino_training_*` settings-kulcsok törlése a JSON-ból.
  - *Elfogadás:* a webes felületen nem indítható DINO-tanítás; YOLO-tanítás és a
    DINO *review* változatlanul működik; grep nem talál `train_dino_head` hivatkozást.
- **B4 [L]** **Review/címkéző felületek egységesítése — egy nézet, két panel**
  (P9). Döntés: NEM modell szerint (dino/yolo), hanem **feladat szerint**
  szervezünk, mert egy képhez kétféle ground truth tartozik:
  - egyetlen `/training/:id/review` képernyő, rajta két, világosan címkézett
    panel: **"Minőség (RQI 1–5)"** (a mai `DinoTrainingView` pontozója) és
    **"Hibák jelölése (poligonok)"** (a mai `TrainingView` + `Canvas`);
  - a `/training/dino/*` útvonalak és a `TRAINING_DINO_*` route-ok megszűnnek;
    a `HomePage.handleTrain` egyetlen `/training/:id/review`-ra navigál (nincs
    több `rqi_display_source`-függő elágazás);
  - a **félrevezető előfeldolgozó kapcsolók** ("Smart ROI / FastSAM",
    Retinex/CLAHE/Geometric ROI/Mask Objects) lekerülnek a pontozó nézetről —
    az éles RQI-modell nyers képen fut, ezek nem befolyásolják a címkét
    (ha diagnosztikára kell, dev-flag mögé);
  - a képre a modell-becslés + P(rossz) *segédinfóként* megjelenhet, hogy a
    címkézőt orientálja (de a mentett érték a humán osztályzat marad);
  - `manual_rqi` vs `manual_dino_rqi` DB-oszlopok tisztázása: melyik az élő
    ground-truth (az export a `manual_rqi`-t használja) → a másik deprecálása.
  - *Elfogadás:* egyetlen review-útvonal; egy képernyőn pontozható ÉS jelölhető
    egy kép; a térképről a "Train/Correct" mindig ide visz; grep nem talál
    `/training/dino` vagy `TRAINING_DINO` hivatkozást; Vitest + typecheck zöld.
- **B2 [S]** **Heurisztika-maradványok** (P2): a 9 halott setting törlése a
  JSON-ból; `analyze_points` alapérték `strategy="YOLO"`-ra; a GraphQL
  típuskomment és a frontend `AnalysisPanel` szövegeinek igazítása.
  *Elfogadás:* a Settings-oldalon csak élő beállítás látszik.
- **B3 [M]** **FastSAM-döntés** (P7): javaslat — **megtartani, de karanténban**:
  a YOLO-tanítóadat-előkészítés még használja (`smart_roi`), tehát amíg YOLO-t
  újratanítunk, kell. Teendő: a `FastSAM-s.pt` a `backend/data/models/` alá,
  útvonala settingből; a `preprocessing.py` docstringjébe kerüljön be, hogy ez
  KIZÁRÓLAG a YOLO-tanítási exportot szolgálja, az RQI-út nyers képeken fut.
  Ha a YOLO-újratanítás lekerül a napirendről, az egész modul törölhető.

### C fázis — Konszolidáció (jövőállóság-alapozás) — ~3 nap

- **C1 [M]** **Egy YOLO-betöltő** (P3): közös `yolo_loader.py` (modellnév →
  ellenőrzött abszolút út feloldás a kanonikus modellkönyvtárból, egyszeri
  betöltés, beállítás-változásra újratöltés); az `inference.py` és a
  `road_analyzer.py` ezt használja; az AI-törmelék kommentek és a halott
  ágak kigyomlálása az `inference.py`-ból; egységes fallback-modell.
  *Elfogadás:* mindkét út ugyanazt a modellt tölti cwd-től függetlenül;
  meglévő tesztek zöldek + új teszt a path-feloldásra.
- **C2 [L]** **Egy kanonikus adatkönyvtár** (P4): döntés a gyökér `data/`
  mellett (a tanítóadat + ml/ már ott van); a `resolve_data_dir` egyszerűsítése
  (env-változóval felülírható, de egyetlen alapértelmezés); a
  `backend/data/images` képeinek átköltöztetése + a DB `image_url`-ok
  ellenőrzése (relatív utak maradnak érvényesek); modellek egy helyre
  (`data/models/`). Futtatás előtt teljes mentés.
  *Elfogadás:* egyetlen images-könyvtár; `ml/extract_features_v2.py` és a
  backend ugyanazt látja; útvonal-feldolgozás füstteszt zöld.
- **C3 [S]** **Settings-séma:** a `settings_manager` kapjon kulcs-regisztert
  (név, típus, default, kategória, "ki használja") — ismeretlen kulcs
  warning-ot logol. Ez tartja tisztán a settingset a jövőben.
- **C4 [S]** REST/GraphQL átfedés (P8): leltár, majd a duplikált végpontok
  deprecálása (a frontend GraphQL-t használ — a REST detect/annotate végpontok
  közül ami nem kell, törlés).

### D fázis — Jövőálló AI-fejlesztési keret — ~2 nap

- **D1 [M]** **Kiértékelési kapu mint szerződés:** az `ml/experiments.py`
  CV-protokollja (fix seed, fix fold-ok, QWK/MAE/bad-AUC riport) legyen a
  hivatalos mérce: `ml/README.md`-ben rögzíteni, hogy **új modell csak akkor
  élesíthető, ha ezen a mérésen ver**; egy `ml/evaluate_artifact.py` szkript,
  ami egy tetszőleges artifactot lemér ugyanezen a protokollon.
- **D2 [S]** **Modell-artifact szerződés dokumentálása:** a joblib-artifact
  kötelező mezői (version, backbone, feature_recipe, thresholds, calibrator,
  cv_metrics, n_train) — ez már de facto létezik, írásba kell foglalni
  (`ml/README.md` + egy betöltés-idejű validáció a `dino_service`-ben,
  értelmes hibaüzenettel).
- **D3 [M]** **P(rossz) kitétele a termékbe:** GraphQL-mező a
  `dino_p_bad`/`dino_score` metaadatnak (már a DB-ben van); a részletkártyán
  megjelenítés; a Settings-oldalra a csak-olvasható **modellkártya**
  (verzió, n_train, CV-metrikák — mind az artifactból jön).
- **D4 [S]** **Doksik hivatkozási rendje:** README gyökérből linkelje a
  MODEL_EXPERIMENTS.md-t, IMPROVEMENT_PLAN.md-t, ml/README.md-t és a
  TrainingGuide.md-t; a TrainingGuide elejére kerüljön oda, hogy a YOLO-ágra
  vonatkozik (az RQI-tanítás az `ml/`-ben él).

### E fázis — Opcionális ML/termék-fejlesztések (amikor időszerű)

- **E1** Célzott címkézés a 3↔4 határon (a maradék hiba ott ül; ~100–200 kép
  a leghatékonyabb befektetés).
- **E2** DINOv3 backbone kipróbálása (HF licenc-elfogadás után; az
  `ml/experiments.py` rácsba egy délután beilleszthető — a D1 kapu megvédi
  az élesítést, ha nem ver).
- **E3** P(rossz)-alapú térképszínezés / útvonal-összegzés (útvonal-szintű
  minőségindex a pontokból).
- **E4** YOLO-modell frissítése az új annotációkból (ekkor dől el a FastSAM
  sorsa is, ld. B3).

---

## 4. Sorrend és függések

```
A1,A2,A3  (függetlenek, azonnal)
   └→ B1, B2  (zsákutcák — B1 előfeltétele a D4 doksi-lezárásnak)
        ├→ B3 (FastSAM-döntés)
        │    └→ C1 (YOLO-egységesítés — B3 után, mert érinti a preprocessing hívóit)
        └→ B4 (review-UI egységesítés — B1 után, mert a DINO-tanítás előbb tűnjön el;
               a D3 P(rossz)-megjelenítés természetes folytatása)
C2 (adatkönyvtár — bármikor, de külön PR-ban, mentéssel)
C3, C4 (függetlenek)
D1, D2 (függetlenek, ML-oldal)
D3 (C-fázistól független, GraphQL + frontend; B4-gyel összevonható)
D4 (B1 után)
```

Becsült teljes ráfordítás: **~10–11 fejlesztői nap** (E fázis nélkül; a B4
review-egységesítés a korábbi becsléshez képest +2 nap).

> **Tipp a kivitelezéshez:** a B4 és a D3 (P(rossz) a részletkártyán/nézetben)
> egy PR-ban a leghatékonyabb — mindkettő a review/detail felületet érinti.

## 5. Amit tudatosan NEM csinálunk

- **Webes RQI-modellválasztó** — ld. 2. szakasz; a display-source kapcsoló marad
  (de a B4 után már csak a *térképi megjelenítést* váltja, nem a címkéző nézetet).
- **Backend nagy átírás / keretrendszer-csere** — a szolgáltatás-rétegzés jó,
  csak gyomlálni kell.
- **RQI 5 osztály feltámasztása** — 14 használható kép van hozzá; ha egyszer
  lesz elég címke, az artifact-formátum és a vágópont-mechanizmus gond nélkül
  kiterjeszthető.
- **Újra-annotálás** — a mérések szerint a mostani címkék a plafonig ki vannak
  használva; célzott pót-címkézés (E1) elég.
