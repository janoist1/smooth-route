# Kátyúőr – RQI modell (tiszta újrakezdés)

Cél: egy Street View képről 1–5 skálán megbecsülni az út minőségét (RQI).
Ez a `ml/` mappa a régi kísérletektől független, tiszta pipeline. Az itt
tanított artifactot a backend `dino_service.py`-ja tölti be; a régi webes
`train_dino_head.py` törölve, a v1 szkriptek az `ml/legacy/`-ban.

## A választott irány (és miért)

**Fagyasztott, előtanított látás-backbone → kicsi ordinális regressziós fej.**

- A régi próbálkozás iránya (DINOv2 jellemzők + fej) valójában jó a kevés
  adathoz. Nem a backbone volt a hiba, hanem a **tanító recept**:
  - ordinális 1–5 skálát 5-osztályos klasszifikációként kezelt
    (`CrossEntropyLoss`) → az 1↔5 tévesztést ugyanúgy bünteti, mint az 1↔2-t;
  - nem volt augmentáció, osztálysúlyozás, rétegzett split és fix seed;
  - a „legjobb modell" mentése a pici, zajos validációs halmazon lényegében
    véletlen checkpointot tartott meg.
- Ezért **regresszióként** tanuljuk (folytonos 1–5 becslés, majd kerekítés),
  augmentációval, osztálybalanszálással, és **kereszt-validációval** értékelünk,
  nem egyetlen split-tel. Empirikusan összevetünk 2 backbone-t (DINOv2 vs CLIP),
  és a CV szerint jobbat tartjuk meg.
- Előbb **auditáljuk a 221 címkét** (lásd lent): ha a jelzés túl zajos, a becsületes
  válasz az, hogy előbb tisztább/nagyobb címkézés kell — ezt is megmondjuk, bizonyítékkal.

## Hol fut mi

- **Tanítás a te Mac-eden** fut (MPS gyorsítással), mert a súlyletöltés + torch
  ott elérhető. A teljes kódot és receptet Claude írja; te egy parancsot futtatsz.
- **Adat-audit, dataset-építés, kiértékelés** a sandboxban fut (numpy/pandas/PIL).

## Lépések

```bash
# 1) Címkék kiexportálása a Postgresből (EGYSZER, a te géped + Docker kell hozzá)
bash ml/export_labels.sh          # -> ml/labels.csv

# 2) Címke-audit (Claude futtatja; te is megnézheted)
python ml/audit_labels.py

# 3) Tanítás – a Mac-eden (a scriptet Claude írja meg a 2) után, az adathoz szabva)
#    -> a v2 pipeline, ld. lent („Pipeline")
```

## RQI skála (megerősítve a `backend/config/analysis_settings.json`-ból)

**1 = Kiváló (sima), 2 = Jó, 3 = Közepes, 4 = Rossz, 5 = elfogadhatatlan.**
Tehát *alacsonyabb szám = jobb út*. (Az RQI 5 osztály a gyakorlatban használhatatlan:
3 meglévő képből egy szálloda-előcsarnok, egy járda — tanításnál eldobjuk.)

## Eredmények

### Őszinte mérés: térbeli CV (2026-11-18), ez a hivatalos szám

A korábbi véletlen 5-fold CV **szivárgott**: a ~10 m-re lévő szomszéd
képkockák (ugyanaz az utca) a tanító- és a tesztoldalra is kerültek. Egy csak
GPS-t látó k-NN (kép nélkül) is QWK 0.884-et ért el rajta. A hivatalos
protokoll mostantól **térben csoportosított** (`ml/spatial_cv.py`): 1 km-es
rácscellák, StratifiedGroupKFold (5 fold, seed=42), beágyazott, térbeli
vágópont-hangolás. Minden kép koordinátája az `ml/image_coords.csv` fájlban van
(`ml/build_coords.py`).

| metrika (v2 bajnok, ugyanaz a modell) | régi, véletlen CV | **térbeli CV, 1 km** | új régió (régió kihagyva) |
|---|---|---|---|
| QWK | 0.889 | **0.774** (95% CI 0.69–0.83) | 0.663 |
| MAE | 0.195 | **0.405** | 0.491 |
| pontos találat | 80.9% | **61.0%** | 52.3% |
| ±1 pontosság | 99.8% | **98.5%** | – |
| rossz út (RQI≥3) AUC | 0.970 | **0.934** | 0.872 |

- **Cellaméret:** a variogram szerint a jegyek hasonlósága ~1 km-ig fogy, 1–5
  km között lapos. A görbe (QWK): 200 m 0.83 → 500 m 0.79 → **1 km 0.79**
  (a hivatalos rácson 0.774) → 2 km 0.77 → 3 km 0.75.
- **Régiók:** az adat 4 gyűjtési területről jön. **Budapesten gyenge** (régión
  belül AUC 0.78, új kerületben QWK 0.23). Vidéken és az agglomerációban a
  jó/rossz döntés jó (AUC 0.95).
- **Osztályok:** a 2-es recallja csak 0.43 (az 1-es 0.83, a 3-as 0.67, a 4-es
  0.60). A tévesztés szinte mindig szomszédos szint.
- **Kísérleti rács térbeli CV-n** (Ridge/SVR/ordinális logisztikus × 7
  jellemző × dinov2-small/base/v3-small + utolsó 2 blokk finomhangolása):
  minden értelmes recept 0.77–0.80 QWK között van, és egyik sem **mérhetően**
  jobb a bajnoknál (páros cella-bootstrap, több rácseltolással ellenőrizve).
  **A v2 recept marad.**
- **Ajánlás:** rögzített független holdout régió; sok helyről kevés kép
  (különösen Budapest); a 2-es osztály élesítése; szakaszszintű aggregálás a
  termékben. Részletek:
  [../docs/MODEL_EXPERIMENTS.md](../docs/MODEL_EXPERIMENTS.md) (6. korszak).

### v2 (2026-07-03, DINOv2-small CLS+patch + hangolt SVR-RBF, 5-fold CV)

> ⚠️ Az alábbi számok a régi, **véletlen** fold-okon készültek, és térbeli
> szivárgás miatt optimisták. A hivatalos szám a fenti térbeli mérés.

**1903 kép** — a 676 hiányzó címkézett kép visszaszerzése után
(`ml/recover_missing_images.py`: a Street View API-ból, pano-dátum őrfeltétellel,
hogy csak a címkézéskor is látott panorámákat töltsük vissza).

| metrika | v2 | v1 (Ridge, 1238 kép) |
|---|---|---|
| MAE | **0.195** | 0.30 |
| pontos találat | **80.9%** | 70.5% |
| ±1 pontosság | **99.8%** | 99.6% |
| QWK | **0.889** | 0.83 |
| rossz út (RQI≥3) találat | **91.9%** | – |
| rossz út AUC | **0.970** | – |

Recept: fagyasztott DINOv2-small **CLS + patch-token átlag** (768 dim, egyetlen
forward pass), StandardScaler + **SVR-RBF** (C=1, eps=0.05), plusz a kerekítés
helyett **hangolt ordinális vágópontok** (a 3|4 határ 3.18-ra csúszott → jobb
rossz-út recall). A számok beágyazott (nested) CV-ből jönnek, szivárgásmentesek.
A dinov2-base ugyanennyit tud (QWK 0.8886) 2× költségért → marad a small.
A DINOv3 ViT-S/16 backbone-t is kipróbáltuk (2026-07-03): a fix 5-fold CV-n
QWK 0.8825 / MAE 0.215 / AUC 0.967 — minden fejmetrikán kicsit gyengébb, a
kapun FAIL, tehát **marad a DINOv2-small v2 recept** (részletek: [../docs/MODEL_EXPERIMENTS.md](../docs/MODEL_EXPERIMENTS.md)).
Az artifact **izotonikus P(rossz út) kalibrátort** és megbízhatósági táblát is
tartalmaz: ha a modell 4-est mond, 80%-ban tényleg 4-es és <1%-ban jó út (1–2).

A tévesztések kivétel nélkül szomszédos szintek (nincs 1↔4 keveredés).
A legrosszabb OOF-hibák kézi átnézés alapján tényleg határeset-utak (foltozott
falusi út, árnyékos kereszteződés), nem címkehibák — a QWK 0.89 közel van az
egy-annotátoros plafonhoz.

### v1 (2026-07-01, fagyasztott DINOv2-small + Ridge, 5-fold CV)

1238 kép (RQI 1–4, nem-út szemét kiszűrve). A jel **valós és tanulható,
újraannotálás nélkül**: MAE 0.30, pontos 70.5%, ±1 99.6%, QWK 0.83.

## Pipeline (minden a Mac-en fut, MPS)

> **New labels (2026-11-26):** the quick-rate screen (`/training/quick`) writes
> into `training_data.manual_rqi` like the review page, so `export_labels.sh`
> exports both. `labels.csv` now also carries `svi_id, latitude, longitude`
> (joined from `street_view_images`) and `source` (`quick` | `review`);
> `build_coords.py` takes sv_* coordinates from there first, then the old
> `missing_labelled_mapped.csv`, then Postgres automatically. The export pins
> `COMPOSE_PROJECT_NAME=smooth-route`, so it also works from a git worktree.

```bash
bash ml/export_labels.sh                       # -> ml/labels.csv (Docker kell)
.venv/bin/python ml/recover_missing_images.py  # hiányzó címkézett képek vissza (Street View API)
.venv/bin/python ml/extract_features_v2.py     # -> ml/cache/{feats_v2_small.npz,clip_v2.npz,dataset_v2.csv}
.venv/bin/python ml/build_coords.py            # -> ml/image_coords.csv (lat/lon + régió minden képhez; commitolva)
.venv/bin/python ml/spatial_analysis.py        # variogram, cellaméret-görbe, GPS-baseline, régió-/osztályhibák
.venv/bin/python ml/experiments.py             # jellemzők x fejek rács, TÉRBELI 5-fold CV (--cv random = régi)
.venv/bin/python ml/tune_svr.py                # SVR hiperparaméter + vágópont hangolás (térbeli fold-ok)
.venv/bin/python ml/finetune_lastblocks.py     # opcionális: utolsó 2 blokk finomhangolása (MPS, ~1 óra)
.venv/bin/python ml/compare_candidates.py      # kihívók páros összevetése a bajnokkal
.venv/bin/python ml/save_model_v2.py           # végső artifact -> ml/cache/rqi_model.joblib
.venv/bin/python ml/evaluate_artifact.py       # ÉLESÍTÉSI KAPU: PASS kell a shiphez
```

Régi (v1) szkriptek: `ml/legacy/` (`extract_features.py`, `train.py`, `save_model.py`) —
referenciának maradnak, az éles artifact a v2 receptből jön.

## Élesítési kapu (KÖTELEZŐ, ne lépd át)

Új vagy módosított `ml/cache/rqi_model.joblib` **csak akkor élesíthető**, ha az
`ml/evaluate_artifact.py` **PASS**-t ad. A szkript a mentett artifact receptjét
és fejét (a pipeline utolsó lépését klónozva) a hivatalos **térbeli** CV-n
méri újra (1 km-es cellák, StratifiedGroupKFold, seed=42, ugyanazok a fold-ok,
mint az `experiments.py`-ban). A vágópontokat beágyazottan, belső térbeli
CV-n hangolja; az artifactba mentett vágópontokat és számokat nem hiszi el.

A jelenlegi bajnok (v2) küszöbei térbeli CV-n (2026-11-18):

| metrika | küszöb | tűrés | irány |
|---|---|---|---|
| QWK | ≥ 0.774 | 0.005 | nagyobb jobb |
| MAE | ≤ 0.405 | 0.005 | kisebb jobb |
| rossz-út AUC | ≥ 0.934 | 0.003 | nagyobb jobb |

A PASS csak azt jelenti, hogy a jelölt nem rosszabb. Jelölt artifactnál a kapu
**páros cella-bootstrapot** is futtat a bajnok ellen. Csak akkor élesíts új
modellt, ha ott „measurably better: YES" jön ki (a ΔQWK 95%-os CI-je 0
fölött van), lehetőleg eltolt rácson is ellenőrizve (`compare_candidates.py`).

```bash
.venv/bin/python ml/evaluate_artifact.py                 # az éles artifactot méri
.venv/bin/python ml/evaluate_artifact.py egy/masik.joblib  # jelöltet mér
# exit 0 = PASS (élesíthető), 1 = FAIL (ne shipeld), 2 = hiba (pl. hiányzó cache)
```

Ha egy új modell veri ezeket, frissítsd a küszöböket az új bajnokra
(`GATE` az `evaluate_artifact.py`-ban) — így a léc mindig a legjobbhoz igazodik.

## Artifact szerződés (`ml/cache/rqi_model.joblib`)

A backend (`backend/app/services/dino_service.py`) betöltéskor validálja az
artifactot (`validate_artifact`), hogy egy hiányos modell ne kriptikus hibával
dőljön el inference közben. A szerződés:

**Strukturálisan kötelező** (hiánya → `ValueError` betöltéskor):
- `pipeline` — a betanított sklearn `Pipeline` (StandardScaler + fej).
- `feature_recipe.keys` — ha van `feature_recipe`, kell benne a `keys` lista
  (mely DINOv2 nézetek/tokenek fűződnek össze). Enélkül a szerviz nem tudja,
  milyen jellemzőt építsen.

**Elvárt v2 metaadat** (hiánya → figyelmeztetés, fallbackkal fut tovább):
- `version` — az artifact sémaverziója (jelenleg 2).
- `backbone` — pl. `facebook/dinov2-small`.
- `feature_recipe` — `{name, keys, needs_clip, crop_top}`.
- `thresholds` — a 3 hangolt ordinális vágópont (hiányában `.5`-kerekítés).
- `p_bad_calibrator` — izotonikus P(rossz út) kalibrátor.
- `cv_metrics` — a beágyazott CV-számok (a modellkártya ezt mutatja).
- `n_train`, `reliability` — tanítóméret és per-osztály megbízhatósági tábla.

A `save_model_v2.py` mindezt beleírja; új mezőt oda és ide (a szerződéshez) is
vezess be, hogy a validáció és a modellkártya konzisztens maradjon.

## Állapot

- [x] Régi projekt átnézve, hibák dokumentálva
- [x] Tiszta `ml/` pipeline váza + audit
- [x] Címkék exportálva (1917 sor; 1241 képpel a lemezen)
- [x] Címke-audit + **képek vizuális átnézése** → skálairány tisztázva, adat viabilis
- [x] Frozen DINOv2 + Ridge baseline, 5-fold CV → **QWK 0.83, MAE 0.30**
- [x] Deployolható modell mentve (`ml/cache/rqi_model.joblib`) + `ml/predict.py`
- [x] Backbone-összevetés: **dinov2-small nyert** (v1: QWK 0.83 > base 0.82; v2-ben döntetlen QWK 0.889 a base 2× költsége mellett)
- [x] Generalizáció ellenőrizve 6 nem-látott képen (mind értelmes)
- [x] **Backend-integráció:** `backend/app/services/dino_service.py` ezt a modellt tölti;
      a route-feldolgozás (`tasks.run_route_processing`) YOLO + DINO CLASSIFICATION passt futtat,
      a térkép a `dino_rqi_score`-t mutatja (`rqi_display_source="dino"`).
- [x] A 676 hiányzó címkézett kép visszaszerzése (`recover_missing_images.py`) → 1903 kép
- [x] Fej-összevetés (Ridge/Huber/SVR/HistGB/MLP × 7 jellemző-variáns): **SVR-RBF nyert**
- [x] Ordinális vágópont-hangolás + izotonikus P(rossz) kalibráció az artifactban
- [x] v2 recept élesítve: `dino_service` a `feature_recipe`-et értelmezi (recept-váltás kódmódosítás nélkül)
- [x] Friss (nem látott) budapesti útvonalakon ellenőrizve: Keleti→Örs vezér tere
      (457 pont) és Csepel (442 pont) — a pontszámok szemre is stimmelnek, a
      `dino_score` + `dino_p_bad` az `analysis_metadata`-ba kerül
- [x] DINOv3 backbone kipróbálva (`--backbone v3small`, HF licenc elfogadva):
      QWK 0.8825 / MAE 0.215 / AUC 0.967 a fix 5-fold CV-n → **nem veri a v2-t**,
      a kapun (`evaluate_artifact.py`) FAIL, ezért maradt a v2 (ld. MODEL_EXPERIMENTS.md)
- [x] **Térbeli CV (2026-11-18):** koordináta mind az 1903 képhez, 1 km-es
      cellás StratifiedGroupKFold kapu, rács újrafuttatva (+ ordinális
      logisztikus fej, utolsó 2 blokk finomhangolása): a bajnok marad, őszinte
      számok QWK 0.774 / MAE 0.405 / AUC 0.934
- [ ] Rögzített, független holdout régió (új kerület + új város), sosem tanítva
- [ ] Több és szórtabb címke (sok helyről kevés kép, főleg Budapest), és a
      2-es osztály élesítése (a hibák zöme 1|2 és 2|3)
- [ ] Szakaszszintű (~100–200 m) aggregálás a termékben, és mérés is ezen a szinten
- [ ] A live artifact `cv_metrics`-e még a régi (0.895) számot mutatja a
      modellkártyán. Újramentéskor (`save_model_v2.py`) már térbeli számok kerülnek bele
- [ ] Opcionális: P(rossz út) megjelenítése a frontend részletkártyán

### Inferencia egy képre
```bash
.venv/bin/python ml/predict.py data/images/<valami>.jpg
# -> RQI=1..4 (excellent/good/fair/poor) + score + P(road) figyelmeztetés
```
A modell a teljes recepttel (`ml/save_model_v2.py`) van betanítva 100% adaton;
a minőség-becslés a fenti CV-szám, nem ezeken a képeken mérve.
