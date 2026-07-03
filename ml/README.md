# Kátyúőr – RQI modell (tiszta újrakezdés)

Cél: egy Street View képről 1–5 skálán megbecsülni az út minőségét (RQI).
Ez a `ml/` mappa a régi kísérletektől független, tiszta pipeline. A régi kód
(`backend/.../dino_service.py`, `train_dino_head.py`) referenciának marad.

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
#    pl.:  python ml/train.py --backbone dinov2_vits14
```

## RQI skála (megerősítve a `backend/config/analysis_settings.json`-ból)

**1 = Kiváló (sima), 2 = Jó, 3 = Közepes, 4 = Rossz, 5 = elfogadhatatlan.**
Tehát *alacsonyabb szám = jobb út*. (Az RQI 5 osztály a gyakorlatban használhatatlan:
3 meglévő képből egy szálloda-előcsarnok, egy járda — tanításnál eldobjuk.)

## Eredmények

### v2 (2026-07-03, DINOv2-small CLS+patch + hangolt SVR-RBF, 5-fold CV)

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

```bash
bash ml/export_labels.sh                       # -> ml/labels.csv (Docker kell)
.venv/bin/python ml/recover_missing_images.py  # hiányzó címkézett képek vissza (Street View API)
.venv/bin/python ml/extract_features_v2.py     # -> ml/cache/{feats_v2_small.npz,clip_v2.npz,dataset_v2.csv}
.venv/bin/python ml/experiments.py             # jellemzők x fejek rács, 5-fold CV
.venv/bin/python ml/tune_svr.py                # SVR hiperparaméter + vágópont hangolás
.venv/bin/python ml/save_model_v2.py           # végső artifact -> ml/cache/rqi_model.joblib
.venv/bin/python ml/evaluate_artifact.py       # ÉLESÍTÉSI KAPU: PASS kell a shiphez
```

Régi (v1) szkriptek: `extract_features.py`, `train.py`, `save_model.py` —
referenciának maradnak, az éles artifact a v2 receptből jön.

## Élesítési kapu (KÖTELEZŐ, ne lépd át)

Új vagy módosított `ml/cache/rqi_model.joblib` **csak akkor élesíthető**, ha az
`ml/evaluate_artifact.py` **PASS**-t ad. A szkript a mentett artifact receptjét
és fejét (a pipeline utolsó lépését klónozva) újramért a hivatalos, fix seed-ű
5-fold CV-n (ugyanazok a fold-ok, mint az `experiments.py`-ban), tehát nem az
artifactba mentett számot hiszi el, hanem függetlenül lemér.

A jelenlegi bajnok (v2) küszöbei (±0.005 tűrés a CV-zajra):

| metrika | küszöb | irány |
|---|---|---|
| QWK | ≥ 0.889 | nagyobb jobb |
| MAE | ≤ 0.195 | kisebb jobb |
| rossz-út AUC | ≥ 0.970 | nagyobb jobb |

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
- [ ] Opcionális: több címkézett adat a 3↔4 határ élesítéséhez (a hibák zöme ott van)
- [ ] Opcionális: P(rossz út) megjelenítése a frontend részletkártyán

### Inferencia egy képre
```bash
.venv/bin/python ml/predict.py data/images/<valami>.jpg
# -> RQI=1..4 (excellent/good/fair/poor) + score + P(road) figyelmeztetés
```
A modell a teljes recepttel (`ml/save_model.py`) van betanítva 100% adaton;
a minőség-becslés a fenti CV-szám, nem ezeken a képeken mérve.
