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

## Eredmények (2026-07-01, fagyasztott DINOv2-small + Ridge, 5-fold CV)

1238 kép (RQI 1–4, nem-út szemét kiszűrve). A jel **valós és tanulható,
újraannotálás nélkül**:

| metrika | érték | naiv baseline |
|---|---|---|
| MAE | **0.30** ± 0.02 | 0.76 |
| pontos találat | 70.5% | – |
| ±1 pontosság | **99.6%** | – |
| QWK (ordinális egyezés) | **0.83** | 0 |

A tévesztések kivétel nélkül szomszédos szintek (nincs 1↔4 keveredés).
Ez már egy lineáris próbafej frozen jellemzőkön — a nagyobb backbone / MLP fej /
ordinális loss / a hiányzó rossz-út képek visszaszerzése mind ráadás, nem szükséglet.

## Pipeline (minden a Mac-en fut, MPS)

```bash
bash ml/export_labels.sh                    # -> ml/labels.csv (Docker kell)
.venv/bin/python ml/audit_labels.py         # címke-audit
.venv/bin/python ml/extract_features.py     # -> ml/cache/{features.npz,dataset.csv}
.venv/bin/python ml/train.py                # 5-fold CV baseline + metrikák
```

## Állapot

- [x] Régi projekt átnézve, hibák dokumentálva
- [x] Tiszta `ml/` pipeline váza + audit
- [x] Címkék exportálva (1917 sor; 1241 képpel a lemezen)
- [x] Címke-audit + **képek vizuális átnézése** → skálairány tisztázva, adat viabilis
- [x] Frozen DINOv2 + Ridge baseline, 5-fold CV → **QWK 0.83, MAE 0.30**
- [x] Deployolható modell mentve (`ml/cache/rqi_model.joblib`) + `ml/predict.py`
- [x] Backbone-összevetés: **dinov2-small nyert** (small QWK 0.83 > base 0.82; kisebb+gyorsabb)
- [x] Generalizáció ellenőrizve 6 nem-látott képen (mind értelmes)
- [x] **Backend-integráció:** `backend/app/services/dino_service.py` ezt a modellt tölti;
      a route-feldolgozás (`tasks.run_route_processing`) YOLO + DINO CLASSIFICATION passt futtat,
      a térkép a `dino_rqi_score`-t mutatja (`rqi_display_source="dino"`).
- [ ] Opcionális: a 676 hiányzó (főleg rossz-út) kép visszaszerzése a balanszért
- [ ] Opcionális: MLP fej / ordinális loss (a lineáris próbafej már QWK 0.83)

### Inferencia egy képre
```bash
.venv/bin/python ml/predict.py data/images/<valami>.jpg
# -> RQI=1..4 (excellent/good/fair/poor) + score + P(road) figyelmeztetés
```
A modell a teljes recepttel (`ml/save_model.py`) van betanítva 100% adaton;
a minőség-becslés a fenti CV-szám, nem ezeken a képeken mérve.
