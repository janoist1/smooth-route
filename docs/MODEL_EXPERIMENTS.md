# Modellkísérletek története — mire jutottunk és hogyan

*Utolsó frissítés: 2026-07-03*

> **Laikus összefoglaló (TL;DR):** A cél az volt, hogy egy Google Street View
> képről a gép megmondja, milyen állapotú az út (1 = kiváló … 4 = rossz).
> Öt megközelítést próbáltunk ki. Az első három (kézi szabályok, hibakereső
> YOLO, út-kivágó FastSAM) vagy nem erre való, vagy nem működött elég jól.
> A negyedik (DINOv2 "látás-agy" + rárakott osztályozó) jó irány volt, de
> rossz recepttel tanítottuk. Az ötödik ugyanez az irány **jó recepttel** —
> ez lett a mostani éles motor: az esetek ~81%-ában pontosan eltalálja az
> osztályzatot, 99.8%-ban legfeljebb egyet téved, és a "jó út vagy rossz út?"
> kérdésre 92%-ban jól válaszol, kalibrált valószínűséggel.

---

## A feladat

Egy 600×400-as Street View képről becsüljük az **RQI**-t (Road Quality Index):

| RQI | jelentés |
|---|---|
| 1 | kiváló (új/sima aszfalt) |
| 2 | jó (enyhe kopás, kevés repedés) |
| 3 | közepes (látható repedéshálók, foltozások) |
| 4 | rossz (mély kátyúk, töredezett felület) |
| 5 | nagyon rossz *(a gyakorlatban nincs elég példa → a modell 1–4-et ad)* |

*Ez a napló a régi (severity) számozást használja: 1 = kiváló … 4 = rossz. A termékben
2026-11-26 óta 5 = Kiváló … 1 = Nagyon rossz; az egyetlen definíció:
[../shared/rqi_scale.json](../shared/rqi_scale.json).*

A tanítóadat kézi címkézésből származik (Postgres `training_data` tábla,
1917 címkézett kép, 2026 januárjában címkézve).

---

## 1. korszak — Kézi szabályok ("heurisztika")

**Mi volt:** klasszikus képfeldolgozás — élsűrűség (repedések), textúra-variancia
(érdesség), folt-sűrűség — kézzel hangolt súlyokkal összegezve, küszöbökkel
RQI-ra váltva.

**Laikusan:** megpróbáltuk *leprogramozni*, hogy mitől néz ki rossznak egy út.

**Miért nem vált be:** az árnyék, a nedves aszfalt, a különböző aszfaltszínek
mind becsapták; a súlyok hangolása vég nélküli kézimunka volt. A kód már
kikerült a rendszerből, de a beállításai (élsűrűség-súly, textúra-osztó,
RQI-küszöbök) **máig ott ülnek a `backend/config/analysis_settings.json`-ban
halott beállításként** — a takarítási terv része az eltávolításuk.

## 2. korszak — YOLO hibadetektálás (él, de más a szerepe)

**Mi volt/van:** YOLOv8 szegmentációs modell (finomhangolva sajátcímkés
úthiba-adatokon: repedés, kátyú, folt, plusz "nem számít" osztályok mint
csatornafedél/árnyék/útburkolati jel), a kép alsó trapéz-régiójában méri a
sérült felület százalékát, és sávokkal RQI-ra váltja
(`backend/app/services/road_analyzer.py` + `rqi_scoring.py`).

**Laikusan:** a gép bekarikázza a kátyúkat, és megméri, a burkolat hány
százaléka sérült.

**Mire jó és mire nem:** a **hibapoligonok** értékesek (a térkép részletkártyán
mutatjuk őket), de RQI-forrásnak gyenge: a "damage% → RQI" leképezés durva, és
ami a YOLO-nak nem "hiba" (egyenetlen, hullámos, kifáradt felület), azt nem
látja. Ezért az RQI-t ma már nem ez adja — de a hibadetektálás **marad**,
mert más kérdésre válaszol ("MI a baj az úttal?", nem "MENNYIRE rossz?").

## 3. korszak — FastSAM útfelület-maszkolás (kísérlet, zsákutca)

**Mi volt:** a FastSAM szegmentáló modellel megpróbáltuk kivágni a képből
csak az útfelületet (a YOLO-tanítóadat előkészítéséhez), hogy a modellek ne
tanuljanak rá az égboltra/házakra.

**Laikusan:** ollóval ki akartuk vágni a képből az utat, mielőtt a gépnek
megmutatjuk.

**Miért nem vált be:** a FastSAM megbízhatatlanul találta meg az utat
(a debug képek — `backend/debug_fastsam_*.jpg` — mutatják a kudarcokat),
geometrikus tartalék-megoldás kellett mellé, és a végén kiderült: **a nyers,
vágatlan kép jobban működik** a DINOv2-alapú osztályozásnak (a 4-5. korszak
kifejezetten nyers képeken tanult és úgy is fut élesben). A kód
(`preprocessing.py`) ma már csak a YOLO-tanítóadat-exportban és az annotáló
felület előnézetében szerepel.

## 4. korszak — DINOv2 + osztályozó fej, v1 recept (jó irány, rossz kivitel)

**Mi volt:** a Meta DINOv2 "látás-agya" (előtanított vizuális jellemzőkinyerő)
lefagyasztva, rá egy kis neurális osztályozó fej, ami az 5 RQI-osztályt
tanulta (`backend/train_dino_head.py` — még webes gomb is volt hozzá).

**Laikusan:** fogtunk egy kész, képekhez nagyon értő mesterséges "szemet",
és csak a végére tanítottunk rá egy kis döntéshozót.

**Miért nem vált be — a három konkrét hiba:**
1. **Osztályozásként kezelte a sorrendet:** az 1↔5 tévesztést ugyanannyira
   büntette, mint az 1↔2-t, pedig előbbi sokkal súlyosabb hiba.
2. **Nem volt augmentáció, osztálykiegyensúlyozás, sem rétegzett
   keresztvalidáció** — kis adatnál ezek nélkül a tanulás zajos.
3. **A "legjobb modell" mentése egy pici, zajos validációs halmazon múlt** —
   gyakorlatilag véletlenszerű checkpointot tartott meg.

A tanulság nem az volt, hogy az irány rossz, hanem hogy **a recept** volt az.

## 5. korszak — Tiszta újrakezdés: az `ml/` pipeline (ez az éles motor)

### v1 alapmérés (2026-07-01)

Fagyasztott DINOv2-small jellemzők + sima **Ridge-regresszió** (folytonos
1–4 becslés, kerekítéssel), **5-fold rétegzett keresztvalidáció** — vagyis a
számok nem "magára tanult" modellről szólnak, hanem mindig nem-látott képeken
mértük őket. Eredmény 1238 képen: **QWK 0.83, MAE 0.30, pontos találat 70.5%**.
Ez bizonyította, hogy a címkék tanulhatók, újraannotálás nélkül.

### v2 (2026-07-03) — a jelenlegi éles modell

Három, egyenként mérhető javítás:

1. **Adat-visszaszerzés:** a 1917 címkéből 676-nak hiányzott a képe a
   lemezről (főleg a JÓ utak példái). A koordinátáik megvoltak az
   adatbázisban, így a Street View API-ból visszatöltöttük őket — egy
   dátum-őrfeltétellel: csak olyan panorámát fogadtunk el, ami már a
   címkézéskor is létezett (nehogy időközben újraaszfaltozott útról tanuljunk
   régi címkével). Tanítóhalmaz: 1238 → **1903 kép**.
2. **Jobb fej:** a Ridge helyett **SVR-RBF** (nemlineáris regresszió) nyert egy
   35-cellás rácskeresésben (7 jellemző-változat × 5 fejtípus, azonos
   fold-okon). A DINOv2 **patch-tokenek átlagát** is hozzáfűztük a CLS-hez
   (a felület-textúra jelet hordozza). Ami NEM segített, azt is megmértük:
   tükrözéses TTA, alsó-kivágás, CLIP-jellemzők hozzáfűzése, nagyobb
   (dinov2-base) backbone — mind ±0-t adott, ezért kimaradtak.
3. **Hangolt vágópontok + kalibráció:** a folytonos becslést nem fix .5-nél
   kerekítjük, hanem tanult határokon (1.51 / 2.47 / 3.18) — a 3|4 határ
   lejjebb csúszása jelentősen javította a rossz utak felismerését. Emellé
   izotonikus **P(rossz út) kalibrátor** került: a modell nem csak osztályzatot
   ad, hanem megbízható valószínűséget is arra, hogy az út rossz (RQI ≥ 3).

**Végeredmény (beágyazott, véletlen 5-fold CV, 1903 kép):**

> ⚠️ **2026-11-18:** az alábbi számok **térbeli szivárgás miatt optimisták**: a
> szomszédos, ~10 m-re lévő képkockák a tanító- és a tesztoldalra is kerültek.
> A valódi, térben csoportosított mérés eredménye QWK 0.774 / MAE 0.405 / AUC
> 0.934; részletek a [6. korszakban](#6-korszak--őszinte-mérés-térben-csoportosított-cv-2026-11-18).

| metrika | v1 (Ridge) | **v2 (éles)** | mit jelent laikusan |
|---|---|---|---|
| QWK | 0.83 | **0.889** | sorrendi egyezés a címkézővel (1 = tökéletes) |
| MAE | 0.30 | **0.195** | átlagosan ~0.2 osztályzatnyit téved |
| pontos találat | 70.5% | **80.9%** | 10-ből 8-szor pontosan eltalálja |
| ±1 pontosság | 99.6% | **99.8%** | gyakorlatilag sosem téved 1-nél többet |
| jó/rossz döntés | – | **91.9%** (AUC 0.970) | "rossz-e az út?" — 92%-ban helyes |

**Megbízhatósági tábla** (mit jelent, ha a modell X-et mond):
ha 1-est ad, a valóság 86%-ban 1-es, 14%-ban 2-es, és **soha** nem 3–4;
ha 4-est ad, 80%-ban tényleg 4-es, 19%-ban 3-as, és <1%-ban jó út.
A tévesztések tehát mindig szomszédos szintek.

**Validáció friss adaton:** két, a tanítás során sosem látott budapesti
útvonalat (Keleti → Örs vezér tere, 457 pont; Csepel, 442 pont) töltöttünk le
és pontoztattunk — a szúrópróbaszerű képellenőrzésen a pontszámok szemre is
helytállók (a Kerepesi út 2-es, a foltozott mellékutcák 3-asok, a vasúti híd
alatti szétrepedt csomópont 4-es, P(rossz)=0.95).

**Hol a hibahatár?** A megmaradt tévesztések kézi átnézés alapján tényleg
határeset-utak (foltozott falusi út, árnyékos kereszteződés) — egyetlen
címkéző önkonzisztenciája kb. ennyi, tehát a QWK 0.89 közel van az adatból
kihozható plafonhoz. Innen már csak több/célzottabb címke visz feljebb,
nem okosabb modell. *(2026-11-18: a 0.89 szivárgott szám volt; a
következtetés, hogy innen a címke visz előre, nem a modell, térbeli CV-n is
áll. Ld. 6. korszak.)*

### DINOv3 backbone kipróbálva (2026-07-03) — nem vert, marad a v2

A v2 recept alternatívájaként kicseréltük a fagyasztott **DINOv2-small**
"látás-agyat" a Meta újabb **DINOv3 ViT-S/16**-jára (`facebook/dinov3-vits16`,
HF-en licenc-kapus — a hozzáférést elfogadtuk). A jellemzőkinyerés (CLS +
patch-token átlag, 384+384=768 dim) *pontosan* a v2 recept; egyetlen apró
technikai eltérés: a DINOv3 a CLS után 4 **register tokent** rak, ezeket a
patch-átlagból kihagyjuk (`extract_features_v2.py`, `num_register_tokens`).

Ugyanazon a fix 5-fold CV-n (seed=42), ugyanazokkal a fold-okkal mértük, mint
a bajnokot — `experiments.py` rács + `tune_svr.py` hangolás:

| mérés | v2 bajnok (DINOv2-small) | DINOv3-small (legjobb) |
|---|---|---|
| rács legjobb cella | cls+patch flipavg svr-rbf | cls+patch+crop svr-rbf |
| QWK (hangolt vágópontokkal) | **0.889** | 0.8825 |
| MAE | **0.195** | 0.215 |
| rossz-út AUC | **0.970** | 0.967 |

**Élesítési kapu (`evaluate_artifact.py`), azonos recept (cls+patch), csak a
backbone cserélve** — a bajnok `rqi_model.joblib` érintése nélkül, oldal-fájlba
mentett jelöltön:

```
DINOv3-small jelölt : QWK 0.886 | MAE 0.207 | bad-AUC 0.966  ->  ❌ FAIL
v2 bajnok (kontroll): QWK 0.895 | MAE 0.188 | bad-AUC 0.970  ->  ✅ PASS
```

**Verdikt:** a DINOv3-small minden fejmetrikán *kicsit* elmarad (QWK −0.006,
MAE +0.02, AUC −0.003), a kapun **megbukik** → **nem élesítjük, marad a v2.**
A nagyobb DINOv3 ViT-B/16-ot nem is futtattuk: ha a v2-nél a base sem adott
hozzá, és a v3-small már így is elmarad, a 2× költségű v3-base sem éri meg.
A DINOv3 backbone ettől függetlenül **első osztályú opció** maradt a pipeline-ban
(`--backbone v3small|v3base` az extract/experiments/tune/save útvonalon), így
később — pl. több címke vagy finomhangolás mellett — egy paranccsal újramérhető.

*A "kipróbáltuk, számokkal, nem segített" is eredmény: dokumentáljuk, hogy ne
kelljen még egyszer elvégezni.*

---

## 6. korszak — Őszinte mérés: térben csoportosított CV (2026-11-18)

> **TL;DR:** a v2-ről korábban közölt QWK 0.889 / MAE 0.195 **térbeli
> szivárgás miatt optimista volt**. Olyan utcákon, amelyeket a modell sosem
> látott, ugyanez a modell **QWK 0.774 / MAE 0.405 / pontos találat 61% /
> rossz-út AUC 0.934**. Új városban (egész régió kihagyva) pedig csak **QWK
> 0.66 / AUC 0.87**. A jó/rossz döntés (AUC 0.93) használható, az 1–4 jegy
> csak nagyjából. A kapu mostantól a térbeli mérést használja. Új modellt nem
> élesítettünk, mert egyik kihívó sem mérhetően jobb.

### Mi volt a baj?

A Street View képek ~10 m-enként követik egymást, ugyanazon az utcán. A régi
véletlen 5-fold CV a tesztkép szomszédját (szinte ugyanazt az aszfaltot) a
tanulóhalmazba tette, így a mérés részben azt nézte, hogy a modell emlékszik-e
az utcára. A legerősebb bizonyíték egy **„csak GPS" modell**: egy k-NN, amely
kizárólag a koordinátát látja, képet egyáltalán nem.

| protokoll | csak GPS (kép nélkül) | v2 bajnok (képből) |
|---|---|---|
| véletlen 5-fold (régi) | **QWK 0.884**, MAE 0.203, AUC 0.960 | QWK 0.889, MAE 0.197, AUC 0.971 |
| térbeli, 1 km cellák (új) | QWK 0.602, MAE 0.603, AUC 0.795 | **QWK 0.774**, MAE 0.405, AUC 0.934 |

A régi protokollon a koordináta önmagában is majdnem a bajnok szintjét hozta,
ezért nem tudta megkülönböztetni az útminőség-felismerést a helyfelismeréstől.
A térbelin a kép érdemben hozzáad (0.60 → 0.77), vagyis a modell tényleg
tanult valamit az útfelületről.

### Koordináta minden képhez

Mind az **1903** címkézett kép kapott koordinátát. 1238 kép a fájlnévből
(`00001_47.4967_19.0694_67.jpg`), 665 `sv_*` kép a DB `street_view_images`
táblájából (a `missing_labelled_mapped.csv` exportból vagy
`build_coords.py --from-db`). Az eredmény a commitolt `ml/image_coords.csv`
(`ml/build_coords.py`). Fontos felismerés: a címkék **csak négy gyűjtési
területről** származnak, eltérő címke-eloszlással.

| terület | képek | 1 / 2 / 3 / 4 |
|---|---|---|
| Budapest, VII–VIII. ker. (Keleti környéke) | 229 | 0 / 111 / 102 / 16 |
| Törökbálint–Budaörs (az összes `sv_*` kép) | 665 | 302 / 291 / 62 / 10 |
| Székesfehérvár déli része | 359 | 233 / 98 / 28 / 0 |
| Tapolca környéke (Balaton-felvidék) | 650 | 5 / 280 / 189 / 176 |

### Csoportosítás: miért 1 km-es rács?

**Variogram** (két kép jegyeltérésének fele a távolság függvényében):

| távolság | 0–20 m | 50–100 m | 200–500 m | 0.5–1 km | 1–2 km | 2–5 km | 5–10 km | >10 km |
|---|---|---|---|---|---|---|---|---|
| γ | 0.11 | 0.23 | 0.40 | 0.49 | 0.53 | 0.54 | 0.91 | 1.03 |

A hasonlóság ~1 km-ig gyorsan fogy, 1 és 5 km között lapos (egy városon belül),
5 km fölött pedig a városok közötti különbség jelenik meg.

**Cellaméret-görbe** (bajnok recept, beágyazott vágópontok; ± = szórás 5
eltolt rácson és fold-seeden):

| protokoll | cellák | QWK | MAE | pontos | rossz-út AUC |
|---|---|---|---|---|---|
| véletlen 5-fold (régi) | – | 0.889 ± 0.002 | 0.197 | 80.6% | 0.971 |
| 200 m | 152 | 0.829 ± 0.007 | 0.307 | 70.2% | 0.945 |
| 500 m | 70 | 0.794 ± 0.007 | 0.377 | 63.4% | 0.934 |
| **1 km (hivatalos)** | 35 | 0.792 ± 0.011 (hivatalos rács: **0.774**) | 0.385 | 63.1% | 0.934 |
| 2 km | 21 | 0.770 ± 0.013 | 0.424 | 59.4% | 0.933 |
| 3 km | 13 | 0.753 ± 0.012 | 0.464 | 55.7% | 0.927 |
| egy régió kihagyva | 4 | 0.663 | 0.491 | 52.3% | 0.872 |

A görbe 500 m és 1 km között ellaposodik, összhangban a variogrammal. Ezért
**1 km a hivatalos cellaméret**: ez a plató konzervatív vége, és megszünteti az
utca-szintű szivárgást. A 2–3 km-es cellák már városrészeket, illetve fél
városokat tartanak vissza, így fokozatosan átmennek a régió-transzfer
mérésébe. Ezt külön, a régió-kihagyásos teszt méri. A hivatalos (eltolás
nélküli) rács 0.774-e a 0.792 ± 0.011-es sáv alsó részén van, tehát a kapu
inkább szigorú, mint engedékeny. A cella-bootstrap 95%-os CI a hivatalos
mérésre: **QWK [0.69, 0.83], MAE [0.34, 0.46], AUC [0.89, 0.97]**. Megjegyzés:
km-es celláknál a StratifiedGroupKFold a seedtől függetlenül ugyanazt a
fold-kiosztást adja, ezért a variancia mérésére a rács eltolása szolgál.

### Az új kapu

`ml/evaluate_artifact.py`: StratifiedGroupKFold (5 fold, 1 km cellák, seed=42).
A vágópontokat minden külső fold tanító részén, **belső térbeli 4-fold** OOF
predikciókon hangoljuk. Korábban a kapu az artifactba mentett, az összes
címkén hangolt vágópontokat használta, ami szintén szivárgás volt. Új
küszöbök: **QWK ≥ 0.774, MAE ≤ 0.405, bad-AUC ≥ 0.934** (tűrés ±0.005 /
±0.005 / ±0.003). A bajnok PASS. Jelölt artifact esetén a kapu a bajnokkal
**páros cella-bootstrapot** is futtat: a jelölt csak akkor „mérhetően jobb",
ha a ΔQWK 95%-os CI-je 0 fölött van.

### A kísérleti rács újra, térbeli CV-n

`ml/experiments.py`: 7 jellemző-változat × 5 fej (Ridge, SVR C∈{0.3,1,3},
**proporcionális esélyű ordinális logisztikus** fej, `ml/heads.py`) × 3
backbone. Minden cella beágyazott vágópontokkal fut. Plusz egy **könnyű
finomhangolás**: a DINOv2-small utolsó 2 blokkja + fej
(`ml/finetune_lastblocks.py`, a fagyasztott rész kimenete gyorsítótárazva, 8
epoch, patch-token dropout; 25 finomhangolás a beágyazott hangolás miatt, kb.
1 óra MPS-en).

| backbone | legjobb cella | QWK | MAE | AUC | a bajnok recept (cls+patch, SVR C=1) ezen a backbone-on |
|---|---|---|---|---|---|
| dinov2-small | all + ordlogit | 0.795 | 0.372 | 0.936 | **0.774 / 0.405 / 0.934 (bajnok)** |
| dinov2-base | cls+patch+crop + ridge | 0.800 | 0.372 | 0.937 | 0.779 / 0.407 / 0.929 |
| dinov3-small | cls+patch+crop + SVR C=3 | 0.781 | 0.400 | 0.932 | 0.746 / 0.448 / 0.921 |
| small, utolsó 2 blokk finomhangolva | – | 0.787 | 0.393 | 0.940 | – |

**Páros összevetés a bajnokkal** (azonos fold-ok, cella-bootstrap, ΔQWK 95% CI;
`ml/compare_candidates.py`):

| kihívó | ΔQWK [95% CI] | ΔMAE | ΔAUC | mérhetően jobb? |
|---|---|---|---|---|
| small, cls+patch flipavg + SVR | +0.014 [−0.001, +0.028] | −0.017 | +0.000 | nem |
| small, cls+patch+crop + ordlogit | +0.014 [−0.006, +0.037] | −0.018 | +0.005 | nem |
| small, all + ordlogit | +0.021 [+0.003, +0.036] | −0.033 | +0.002 | a hivatalos rácson igen, de lásd lent |
| base, cls+patch + SVR | +0.005 [−0.026, +0.029] | +0.003 | −0.005 | nem |
| base, all + ordlogit | +0.021 [−0.011, +0.055] | −0.036 | −0.005 | nem |
| small, finomhangolás (2 blokk) | +0.012 [−0.007, +0.038] | −0.012 | +0.005 | nem |

Az egyetlen „igen" (all + ordlogit) a ~100 cellából utólag kiválasztott
legjobb, ezért a nyertes-torzítás miatt külön ellenőriztük 6 eltolt rácson: a
ΔQWK 5-ből 6 esetben pozitív (átlag ~+0.015), de a CI csak 1 esetben van 0
fölött, az AUC-különbség pedig mindenhol ~0. A base + Ridge 4 rácson
−0.011 és +0.022 között mozog. Emellett az all + ordlogit élesítéséhez CLIP
kellene inference-kor (második backbone) és új fejosztály a backendben.

**Verdikt:** térbeli CV alatt minden értelmes recept egy ~0.77–0.80 QWK-s
sávban van, a különbségek a mérési zajon belül maradnak. **A jelenlegi recept
(DINOv2-small cls+patch + SVR) marad. Új modellt nem élesítettünk.** Amit a
régi rács „nyertesnek" mutatott (SVR > minden más, small ≈ base), az térbeli
CV-n sem cáfolódik, de nem is erősödik meg. A finomhangolás és a nagyobb
backbone sem hoz mérhető javulást ennyi adaton. Az ordinális logisztikus fej
olcsó és a bajnokkal egyenrangú (cls+patch: 0.775 vs 0.774), így jó tartalék.

### Hibaelemzés (hivatalos protokoll, a bajnok OOF predikciói)

**Régiónként** (azonos predikciók, régióra szűrve; régión belül kisebb a
jegyek szórása, ezért a QWK itt alacsonyabb, mint az egészen):

| régió | n | QWK | MAE | pontos | rossz-út AUC | torzítás (becsült − valós) |
|---|---|---|---|---|---|---|
| **Budapest** (VII–VIII.) | 229 | 0.404 | 0.397 | 62% | **0.776** | +0.13 |
| **vidék + agglomeráció** együtt | 1674 | 0.783 | 0.406 | 61% | 0.947 | −0.06 |
| – Törökbálint–Budaörs | 665 | 0.574 | 0.453 | 57% | 0.932 | −0.13 |
| – Székesfehérvár | 359 | 0.561 | 0.326 | 68% | 0.931 | −0.09 |
| – Tapolca környéke | 650 | 0.695 | 0.402 | 61% | 0.905 | +0.04 |

**Ha egy egész régiót kihagyunk** (3 régión tanítunk, a 4.-en mérünk), a
modell a tanítóhalmaz átlaga felé húz:

| kihagyott régió | QWK | MAE | AUC | átlagos valós / becsült jegy |
|---|---|---|---|---|
| Budapest | **0.226** | 0.485 | **0.763** | 2.64 / 2.29 |
| Törökbálint–Budaörs | 0.622 | 0.415 | 0.940 | 1.67 / 1.94 |
| Székesfehérvár | 0.413 | 0.499 | 0.872 | 1.43 / 1.91 |
| Tapolca környéke | 0.365 | 0.568 | **0.717** | 2.72 / 2.40 |

**Budapest a gyenge pont.** Csak 229 kép, egyetlen városrészből, nincs benne
1-es jegy, és a városi kép (villamossín, kockakő, parkoló autók, árnyék) más,
mint a vidéki. Régión belül is csak AUC 0.78, egy új budapesti kerületben
pedig QWK 0.23. A vidéki és agglomerációs utakon a jó/rossz döntés megbízható
(AUC 0.95).

**Osztályonként** (sor = valós, oszlop = becsült):

| valós \ becsült | 1 | 2 | 3 | 4 | recall |
|---|---|---|---|---|---|
| 1 | 448 | 92 | 0 | 0 | 0.83 |
| 2 | 254 | 335 | 176 | 15 | **0.43** |
| 3 | 6 | 63 | 257 | 55 | 0.67 |
| 4 | 0 | 7 | 74 | 121 | 0.60 |
| precision | 0.63 | 0.67 | 0.51 | 0.63 | |

A tévesztések továbbra is szinte mind szomszédosak (±1: 98.5%; 1↔4 nincs), de
a **2-es a probléma**: a valódi 2-esek több mint fele 1-esnek vagy 3-asnak
látszik. A régi „ha 1-est mond, sosem 3–4" garancia nagyjából tartja (6/708),
a „ha 4-est mond, 80%-ban 4-es" viszont térbeli CV-n csak 63%.

### Ajánlás: mi kell a megbízhatósághoz?

1. **Független holdout régió, rögzítve.** Egy új, címkézetlen régiót (pl. egy
   másik budapesti kerületet és egy új vidéki várost) előre jelöljünk ki tiszta
   tesztnek, amelyen sosem tanítunk és hangolunk. A térbeli CV a fejlesztéshez
   jó, de a „mennyire működik új helyen" kérdésre csak ez ad tiszta választ (ma
   a régió-kihagyásos becslés: QWK 0.66 / AUC 0.87).
2. **Több és szórtabb címke, nem több ugyanabból.** A 1903 kép valójában 4
   terület ~35 km²-nyi utcája. A szomszédos képkockák alig adnak új
   információt (a variogram 20 m-en belül γ=0.11). Hatékonyabb **sok helyről
   kevés kép** (pl. 100–200 m-enként egy), sok különböző településről, és
   célzottan **Budapestről** (minden útkategóriával, 1-esekkel is).
3. **A 2-es osztály definíciójának élesítése.** A 2-esek 57%-át téveszti a
   modell. Egy második címkéző ~200 képen megmutatná, mennyi ebből a
   címkezaj (inter-annotátor egyezés); a `TrainingGuide.md` 1|2 és 2|3
   határpéldáit érdemes bővíteni.
4. **Szegmensszintű aggregálás a termékben.** Egy utcaszakaszra 10–50 képkocka
   jut, és a szomszédos képek erősen korrelálnak. Ezért ne egyetlen képkocka
   jegyét mutassuk: aggregáljunk ~100–200 m-es szakaszra (P(rossz) átlaga,
   medián jegy). Ez a zajos 2|3 határesetek egy részét kisimítja. Mérni is
   szakaszszinten kellene: a következő kiértékelés aggregált jegyre számoljon
   QWK-t.
5. **A kommunikált számok.** A modellkártya (`cv_metrics` a live artifactban)
   még a régi 0.895-öt mutatja. A `save_model_v2.py` már térbeli számokat ír,
   de a bajnokot nem mentettük újra, mert az a vágópontokat és a kalibrátort is
   megváltoztatná. Ezt külön döntésként érdemes megtenni.

Reprodukálás:

```bash
.venv/bin/python ml/build_coords.py          # -> ml/image_coords.csv
.venv/bin/python ml/spatial_analysis.py      # variogram, cellaméret-görbe, GPS-baseline, régió-/osztályhibák
.venv/bin/python ml/experiments.py --backbone small|base|v3small
.venv/bin/python ml/finetune_lastblocks.py --images-dir data/images
.venv/bin/python ml/compare_candidates.py    # páros összevetés a bajnokkal
.venv/bin/python ml/evaluate_artifact.py     # kapu (PASS a bajnokra)
```

## Era 7 — Segment-level aggregation (2026-11-26)

> **TL;DR:** the map shows road segments, not single frames, so we measured
> the model at segment level, under the same spatial protocol as Era 6.
> Taking the **median frame score over a ~200 m segment** (with cut-points
> re-tuned for the aggregated score) lifts agreement with the human segment
> label from **QWK 0.78 → 0.84, MAE 0.40 → 0.29, exact class 61% → 71%,
> bad-road AUC 0.94 → 0.97**. The gain is real but modest, because
> neighbouring frames share most of their error: averaging cannot remove an
> error that the whole segment has in common. Two useful consequences:
> **(1)** a few frames per segment are as good as twenty: a frame every
> **50 m, plus a second pass at 30 m on the low-confidence fifth of the
> road**, gives the same segment quality as today's 10 m with **26% of the
> frames** (a plain 30 m spacing: 33%); **(2)** how sure we are about a
> segment depends on how far its score is from the nearest cut-point, hardly
> on the number of frames or their spread. One limit: in **Budapest**, the region the model
> already reads worst, aggregation does not help. The recipe for the backend
> is `ml/segment_recipe.json`. No model was changed.

### What was measured

Everything comes from `ml/segment_eval.py` (one command, prints every table
below).

- **Frame predictions:** the champion's out-of-fold predictions under the
  official protocol (1 km cells, StratifiedGroupKFold 5, seed 42, nested
  cut-points): QWK 0.774 / MAE 0.405 / AUC 0.934, identical to the gate.
  Saved to `ml/cache/oof_spatial_champion.csv` (score, class, P(bad), fold).
  P(bad) is an isotonic calibrator fitted inside each fold.
- **Chains:** frames in capture order; a chain breaks at a gap > 40 m, at a
  turn > 45°, and at a 1 km cell border. The last rule guarantees that a
  segment never straddles train and test. Result: 91 chains, 19.5 km, frames
  ~10 m apart.
- **Segments:** every chain is cut into equal pieces of about L metres,
  L ∈ {1 frame, 50, 100, 150, 200, 300 m}. **Segment truth = the median human
  label** of its frames.
- **Honest tuning:** aggregation shrinks the spread of the scores, so the
  score → class cut-points are re-tuned for every aggregator and length, on
  the training folds only (their inner out-of-fold frame scores, aggregated
  the same way). Test labels never touch a cut-point.
- **Metrics** are weighted by segment length. Confidence intervals resample
  whole cells (1000 times). Every length is also cut three ways (cuts shifted
  by 0, ⅓ and ⅔ of a segment); the "mean of 3 segmentations" is the steadier
  number, because a single segmentation moves QWK by ±0.01–0.02.

Single-frame numbers in this section are length-weighted (QWK 0.780), so they
differ slightly from the official per-image 0.774.

### How homogeneous are real segments?

Human labels inside one segment (shares of road length):

| segment length | segments | frames / segment | all labels identical | good and bad frames mixed | frames equal to the segment label |
|---|---|---|---|---|---|
| 50 m | 412 | 5 | 57% | 24% | 86% |
| 100 m | 225 | 10 | 40% | 35% | 82% |
| 150 m | 169 | 14 | 29% | 40% | 80% |
| **200 m** | 143 | 18 | 25% | 46% | 79% |
| 300 m | 118 | 26 | 18% | 51% | 77% |

Road quality changes slowly: even in a 200 m segment four of five frames
carry the segment's label. But a longer segment does hide short bad patches:
at 200 m almost half of the road lies in segments that contain both good
(1–2) and bad (3–4) frames.

### Why averaging helps less than expected

If frame errors were independent, 18 frames would cut the noise by a factor
of four. They are not independent:

| distance between two frames of one chain | 10 m | 20 m | 30 m | 50 m | 100 m | 200 m |
|---|---|---|---|---|---|---|
| correlation of the model's error | 0.65 | 0.54 | 0.50 | 0.42 | 0.32 | 0.19 |

The model is wrong about a *stretch of road*, not about a frame. The share of
the frame-error variance that all frames of a segment have in common, and
that no aggregator can remove, is 65% at 50 m, 55% at 100 m and still 46% at
200 m.

### Aggregators × segment length

QWK / MAE, mean of the 3 segmentations (single frame: **0.780 / 0.404**):

| aggregator | 50 m | 100 m | 150 m | 200 m | 300 m |
|---|---|---|---|---|---|
| **median score** | 0.790 / 0.387 | 0.819 / 0.328 | 0.834 / 0.320 | **0.843 / 0.292** | 0.848 / 0.281 |
| mean score | 0.812 / 0.353 | 0.824 / 0.325 | 0.833 / 0.307 | 0.852 / 0.272 | 0.867 / 0.248 |
| trimmed mean (20% per side) | 0.802 / 0.365 | 0.809 / 0.355 | 0.816 / 0.334 | 0.866 / 0.245 | 0.856 / 0.241 |
| mean P(bad) | 0.809 / 0.363 | 0.826 / 0.328 | 0.840 / 0.302 | 0.881 / 0.223 | 0.847 / 0.259 |
| majority vote of frame classes | 0.792 / 0.385 | 0.802 / 0.363 | 0.810 / 0.360 | 0.811 / 0.358 | 0.807 / 0.357 |
| mean of integer frame classes | 0.806 / 0.356 | 0.823 / 0.331 | 0.824 / 0.327 | 0.842 / 0.295 | 0.840 / 0.280 |

- **Length matters more than the aggregator.** Agreement rises steadily with
  length and flattens around 200 m. Median, mean, trimmed mean and mean
  P(bad) stay within ±0.02 of each other, which is the noise of one
  segmentation; in a paired test none of them is measurably better than the
  median at 100–300 m (the largest gap, mean P(bad) at 200 m, is +0.026
  [−0.007, +0.074]). **Majority vote is the one clear loser** (−0.047
  [−0.093, −0.005] at 200 m): it throws away how far each frame is from a
  class border.
- **The paired gain over the single frame** (median score, cell bootstrap):
  50 m +0.015 [−0.005, +0.034], 100 m +0.026 [−0.015, +0.060], 150 m +0.037
  [−0.020, +0.074], **200 m +0.079 [+0.029, +0.119]**, 300 m +0.093 [+0.063,
  +0.125]. Up to 150 m the gain cannot be told from zero; at 200 m it can.
- **Re-tuning the cut-points pays off from 150 m up**: at 200 m QWK 0.843
  with re-tuned cut-points vs 0.821 with the single-frame cut-points (MAE
  0.292 vs 0.339). At 50–100 m it makes no difference.

The recommended recipe against the single frame:

| metric | single frame | 200 m median, one segmentation [95% CI] | mean of 3 segmentations | paired gain [95% CI] |
|---|---|---|---|---|
| QWK | 0.780 [0.70, 0.84] | 0.859 [0.76, 0.92] | **0.843** | +0.079 [+0.029, +0.119] |
| MAE | 0.404 [0.33, 0.46] | 0.264 [0.18, 0.35] | **0.292** | −0.139 [−0.214, −0.061] |
| exact class | 61.1% | 73.6% | **70.8%** | |
| within ±1 | 98.6% | 100% | | |
| bad-road (RQI ≥ 3) AUC | 0.940 [0.90, 0.97] | 0.968 [0.91, 1.00] | **0.968** | +0.028 [−0.001, +0.054] |
| good/bad accuracy | 86.7% | 90.4% | **89.4%** | |

Confusion at 200 m (unshifted segmentation), in km of road (rows = human
segment label):

| truth \ predicted | 1 | 2 | 3 | 4 | recall |
|---|---|---|---|---|---|
| 1 | 4.88 | 0.83 | 0 | 0 | 0.85 |
| 2 | 2.05 | 4.97 | 1.10 | 0 | **0.61** |
| 3 | 0 | 0.78 | 2.56 | 0.25 | 0.71 |
| 4 | 0 | 0 | 0.13 | 1.90 | 0.94 |
| precision | 0.70 | 0.76 | 0.68 | 0.88 | |

Class 2 is still the weakest (recall 0.61, up from 0.43 per frame), but a
predicted 4 is now right 88% of the time (63% per frame) and nothing is off
by more than one class.

**What aggregation does not do:** it does not make individual frames more
accurate. If every frame simply shows its segment's class and is judged
against its own label, QWK is 0.76–0.79 at every length (single frame
0.780). Smoothing each frame with its neighbours (Gaussian, σ = 25–100 m)
gives +0.014 to +0.018 QWK, not distinguishable from zero. A segment is a
more reliable *statement about a stretch of road*, not a sharper picture of
each spot.

### Confidence

The backend computes, per segment,

`confidence = clamp((1 − exp(−n / n_ref)) · exp(−(iqr / spread_ref)²) · (0.5 + 0.5 · min(1, margin / margin_ref)), 0, 1)`

with n = frames in the segment, iqr = interquartile range of the frame
scores, margin = distance of the aggregated score from the nearest cut-point.
What predicts that the segment class is right (200 m, median score, the 3
segmentations pooled):

| margin | 0–0.1 | 0.1–0.2 | 0.2–0.3 | 0.3–0.4 | 0.4–0.5 | 0.5–0.7 | > 0.7 |
|---|---|---|---|---|---|---|---|
| P(class correct) | 0.56 | 0.68 | 0.70 | 0.76 | 0.89 | 0.95 | 1.00 |
| P(good/bad wrong) | 25% | 11% | 6% | 4% | 0% | 0% | 0% |

| frames used (segment thinned at random) | 1 | 2 | 3 | 5 | 8 | all (~18) |
|---|---|---|---|---|---|---|
| P(class correct) | 0.64 | 0.67 | 0.68 | 0.68 | 0.68 | 0.71 |

| IQR of frame scores | < 0.1 | 0.1–0.15 | 0.15–0.2 | 0.2–0.3 | 0.3–0.4 | > 0.4 |
|---|---|---|---|---|---|---|
| P(class correct) | 0.70 | 0.67 | 0.79 | 0.67 | 0.69 | 0.69 |

- **The margin carries the signal.** A segment that sits on a cut-point is a
  coin flip between two neighbouring classes; half a class away it is
  almost always right.
- **The number of frames barely matters** (one frame 0.64, eighteen 0.71),
  which follows from the correlated errors above.
- **The spread of the scores does not predict a wrong class.** It only goes
  with more good/bad mistakes (0–2% below an IQR of 0.15, 11–15% above 0.2).

Fitted parameters (least Brier score against "segment class correct"; among
fits that cannot be told apart the more cautious one is taken):
**n_ref = 0.5, spread_ref = 2.0, margin_ref = 0.6**. With these the formula
is in practice a function of the margin: n only penalises a single-frame
segment (×0.86), and the IQR term stays above 0.92 for 95% of segments. Fitting
on four folds and checking on the fifth gives the same parameters (n_ref 0.5,
spread_ref 1.5–2.0, margin_ref 0.6–0.7) and this calibration:

| confidence | share of road | mean confidence | P(class correct) | P(good/bad wrong) |
|---|---|---|---|---|
| < 0.50 | 7% | 0.47 | 0.61 | 28% |
| 0.50–0.55 | 18% | 0.53 | 0.57 | 21% |
| 0.55–0.60 | 17% | 0.58 | 0.69 | 19% |
| 0.60–0.65 | 12% | 0.62 | 0.68 | 0% |
| 0.65–0.70 | 10% | 0.67 | 0.71 | 0% |
| 0.70–0.75 | 10% | 0.72 | 0.75 | 12% |
| 0.75–0.80 | 6% | 0.78 | 0.60 | 4% |
| 0.80–0.90 | 12% | 0.84 | 0.90 | 0% |
| 0.90–1.00 | 8% | 0.96 | 0.97 | 0% |

The confidence is roughly the probability that the class is right. The
single bins are noisy (27–73 pooled segments each), so the map should use
three levels:

| level | rule | share of road | P(class correct) | P(good/bad wrong) | off by 2 classes |
|---|---|---|---|---|---|
| **high** | confidence ≥ 0.80 | 19% | **0.93** | 0% | 0% |
| **medium** | 0.55 – 0.80 | 56% | **0.69** | 9% | 0% |
| **low** | < 0.55 | 25% | **0.58** | 23% | 0% |

(Cross-fold parameters, full segments. With the final parameters: 0.93 / 0.70
/ 0.53. With thinned segments included: 0.88 / 0.67 / 0.53.) "High" is
reliable in every region (0.87–1.00); "low" and "medium" are not equally well
separated everywhere (see the regions below). A predicted 3 never reaches
"high": its score band is only ~0.55 wide, so it is always close to a
cut-point. That matches reality (precision of class 3 is 0.68).

**A simpler signal for the good/bad call.** If the map mainly says "good" or
"bad", the distance of the segment score from the good|bad cut-point (t23)
alone is the cleanest indicator: P(good/bad wrong) is 64% within 0.1 of it,
22% at 0.1–0.2, 16% at 0.2–0.3, 5–6% at 0.3–0.8 and 0% beyond 0.8 (46% of
the road). A second, good/bad-specific confidence built on this distance
would be more informative than the n and IQR terms of the current formula.

### How dense must the frames be?

The collector takes a frame every ~10 m (`route_collector.py`,
`interval_meters=10`), and every frame costs Street View quota. We thinned the
labelled runs and re-measured the 200 m recipe: same segments, same truth
(the median of *all* human labels), same cut-points; only the frames the
model may use change. Every number is the mean of the 3 segmentations and of
all offsets of the thinning; intervals resample cells; Δ is the paired
difference to the dense result on the same segments. Bad-segment recall =
share of the truly bad segment length that is predicted bad.

**(a) Uniform spacing**

| spacing | frames used | QWK | MAE | exact | bad AUC | bad-segment recall |
|---|---|---|---|---|---|---|
| 10 m (today) | 100% | 0.843 [0.74, 0.91] | 0.292 [0.21, 0.37] | 70.8% | 0.968 [0.91, 1.00] | 0.81 [0.60, 0.95] |
| 20 m | 50% | 0.845 [0.75, 0.91] | 0.282 [0.21, 0.35] | 72.1% | 0.965 [0.91, 0.99] | 0.85 [0.69, 0.95] |
| 30 m | 33% | 0.848 [0.75, 0.91] | 0.276 [0.20, 0.34] | 72.6% | 0.965 [0.91, 1.00] | 0.85 [0.67, 0.95] |
| 50 m | 20% | 0.824 [0.71, 0.89] | 0.315 [0.24, 0.39] | 68.9% | 0.962 [0.91, 0.99] | 0.82 [0.66, 0.94] |
| 100 m | 10% | 0.808 [0.68, 0.88] | 0.329 [0.26, 0.40] | 67.9% | 0.952 [0.89, 0.99] | 0.82 [0.64, 0.94] |

| paired difference to 10 m | ΔQWK | ΔMAE | ΔAUC | Δ bad-segment recall |
|---|---|---|---|---|
| 20 m | +0.004 [−0.017, +0.026] | −0.012 [−0.046, +0.019] | −0.002 [−0.007, +0.002] | +0.042 [−0.026, +0.123] |
| 30 m | +0.008 [−0.010, +0.030] | −0.019 [−0.052, +0.011] | −0.002 [−0.006, +0.002] | +0.037 [−0.013, +0.102] |
| 50 m | −0.014 [−0.039, +0.010] | +0.020 [−0.020, +0.057] | −0.005 [−0.012, +0.001] | +0.015 [−0.049, +0.093] |
| 100 m | −0.023 [−0.050, +0.006] | +0.034 [−0.012, +0.073] | −0.012 [−0.026, −0.002] | +0.025 [−0.041, +0.105] |

- **50 m is not measurably worse than 10 m.** Every interval contains zero,
  and bad segments are found as often as with dense frames.
- **It is not proven equal either.** The interval still allows a loss of 0.04
  QWK. 20 m and 30 m are safely within 0.02 of dense. At 100 m a loss shows
  in the AUC.
- The two-pass results below settle it: frames added only on the unsure
  fifth of the road improve on the 50 m pass by +0.019 [+0.007, +0.034]. So
  uniform 50 m does leave about 0.02 QWK on the table; the direct comparison
  to 10 m is just too noisy to show it.

**(b) Two-pass collection.** A sparse first pass, then a denser second pass
only on the segments the first pass is unsure about. Triggers, all computed
from the first-pass frames: *low* = confidence < 0.55 (the formula above),
*near a cut-point* = margin < 0.15, *bad* = class ≥ 3.

| strategy | frames used | road re-visited | QWK | ΔQWK vs 10 m | ΔQWK vs its first pass alone | Δ bad-segment recall vs 10 m | bad frames photographed |
|---|---|---|---|---|---|---|---|
| 50 → 10 m if low, near a cut-point or bad (the proposed rule) | 60% | 52% | 0.838 | +0.001 [−0.004, +0.006] | +0.014 [−0.007, +0.038] | −0.002 [−0.005, 0.000] | 84% |
| 50 → 10 m if low or bad | 53% | 42% | 0.840 | +0.003 [−0.002, +0.010] | +0.016 [−0.003, +0.040] | −0.003 [−0.009, 0.000] | 80% |
| 50 → 10 m if bad | 43% | 29% | 0.832 | −0.005 [−0.020, +0.009] | +0.008 [−0.009, +0.025] | **−0.032 [−0.069, 0.000]** | 75% |
| 50 → 10 m if low | 36% | 21% | 0.840 | +0.003 [−0.007, +0.015] | +0.016 [+0.001, +0.037] | +0.020 [−0.006, +0.055] | 38% |
| **50 → 30 m if low** | **26%** | 21% | 0.843 | +0.005 [−0.012, +0.029] | **+0.019 [+0.007, +0.034]** | +0.028 [−0.038, +0.099] | 27% |
| 100 → 30 m if low | 17% | 25% | 0.833 | +0.002 [−0.016, +0.028] | +0.025 [+0.013, +0.041] | +0.018 [−0.055, +0.093] | 18% |
| uniform 30 m | 33% | – | 0.848 | +0.008 [−0.010, +0.030] | – | +0.037 [−0.013, +0.102] | 33% |
| uniform 50 m | 20% | – | 0.824 | −0.014 [−0.039, +0.010] | – | +0.015 [−0.049, +0.093] | 20% |

- **The second pass works, and "low confidence" is the trigger that does the
  work.** It provably improves on the first pass alone and brings the result
  back to the dense one.
- **Adding "near a cut-point" and "bad" to the trigger buys nothing for
  segment quality.** The re-visited share of the road goes from 21% to 52%
  and the frames from 36% to 60%, for the same result. Re-visiting *only* the
  bad segments is harmful: bad-segment recall drops by 3 points, because a
  one-sided re-check can only take bad flags away.
- **30 m is dense enough for the second pass.** Going down to 10 m costs 36%
  instead of 26% of the frames and changes nothing.
- **Per frame spent.** Call a strategy proven if the lower end of its ΔQWK
  interval is above −0.02. The cheapest proven ones are 100 → 30 m if low
  (17% of the frames), 50 → 30 m if low (26%) and uniform 30 m (33%).
  Uniform 50 m and 100 m are not proven. The differences among the proven
  ones are within noise.

**Recommendation: 50 m everywhere, then 30 m on the low-confidence
segments.** It needs 26% of today's frames (about 4× the road per quota), is
provably better than 50 m alone and cannot be told from 10 m. If a second
pass is not worth building, **uniform 30 m** (33%) is the single-pass
equivalent. A 100 m first pass is cheaper still and passes the same test, but
we do not recommend it: two frames per segment leave the median no protection
against a junk frame (non-road and unusable views are not yet filtered in
production, and the labelled set contains none), and it sees the fewest short
defects.

**Short defects.** A defect visible in only one or two frames is a different
question from segment quality. Runs of consecutive human-bad frames:

| run of bad frames | runs | share of all bad road | the model calls such a frame bad | its 200 m segment is painted bad (dense frames) | run photographed at 30 / 50 / 100 m |
|---|---|---|---|---|---|
| 1 frame (~10 m) | 46 | 8% | 69% | 49% | 33% / 20% / 10% |
| 2 frames | 21 | 7% | 91% | 64% | 67% / 40% / 20% |
| 3–4 frames | 25 | 16% | 81% | 62% | 100% / 68% / 34% |
| 5–9 frames | 25 | 28% | 96% | 84% | 100% / 100% / 62% |
| 10+ frames (100 m+) | 11 | 41% | 87% | 81% | 100% / 100% / 100% |

- 85% of the bad road is in runs of at least 30 m. That is what a segment
  colour can show, and it is found equally well at every spacing up to 50 m.
- Defects one or two frames long are 15% of the bad road. **A 200 m segment
  hides a third to a half of them even with dense frames**, because its class
  is the median. Sparse sampling is not what loses them at segment level.
- Showing them needs a separate frame-level defect layer, and that layer does
  need the frames: at 30 m a third of the single-frame defects are
  photographed, at 50 m a fifth. The proposed rule (50 → 10 m if low, near a
  cut-point or bad) photographs 84% of all bad frames and 55% of the isolated
  ones for 60% of the frames; the rest lie in segments that look confidently
  good. If single defects must be on the map, that is the strategy to use.
  For segment quality alone it spends more than twice the frames for nothing.

The confidence levels keep their meaning with fewer frames (P(class correct)
for high / medium / low: 0.89 / 0.71 / 0.61 at 30 m, 0.88 / 0.69 / 0.51 at
50 m). The picture is the same for shorter segments (100 m: QWK 0.819 → 0.809
at 30 m → 0.774 at 100 m). Caveat: this is thinning of dense, hand-checked
runs; real sparse collection also meets frames the labelled set does not
contain (junk views, occlusions), which is why the recipe uses the median and
asks for at least 2 frames.

### Regions: does the bias survive aggregation?

Single frame → 200 m segments (mean of the 3 segmentations):

| region | frames → segments | QWK | MAE | bad AUC | good/bad acc. | class bias | score bias |
|---|---|---|---|---|---|---|---|
| Budapest (VII–VIII.) | 229 → 13 | 0.44 → **0.34** | 0.37 → 0.37 | 0.79 → 0.83 | 70% → **65%** | +0.10 → −0.20 | +0.02 → 0.00 |
| Törökbálint–Budaörs | 665 → 40 | 0.58 → 0.63 | 0.45 → 0.35 | 0.93 → 0.97 | 92% → 97% | −0.14 → −0.11 | 0.00 → −0.01 |
| Székesfehérvár | 359 → 26 | 0.53 → 0.60 | 0.33 → 0.21 | 0.93 → n/a¹ | 94% → 96% | −0.10 → +0.02 | +0.06 → +0.03 |
| Tapolca area | 650 → 64 | 0.71 → 0.84 | 0.41 → 0.25 | 0.92 → 0.95 | 83% → 87% | −0.01 → +0.01 | −0.18 → −0.19 |

Bias = model − human, in classes (class bias) and on the continuous score
(score bias); + means the model says worse than the human.
¹ no bad segment is left in Székesfehérvár at 200 m.

- **A regional score offset survives aggregation untouched**, as it must: it
  is the same for every frame of a segment. Around Tapolca the model's score
  is 0.18 better than the human label before and 0.19 after.
- **Budapest does not benefit.** Outside Budapest every region improves; in
  Budapest QWK falls from 0.44 to 0.34 and the good/bad accuracy from 70% to
  65%. Its frame-level "too severe" (+0.10 class) turns into "too lenient"
  (−0.20) with the segment cut-points, while its score bias is ~0: the
  problem there is the good|bad decision itself, not an offset, and
  aggregation cannot repair it. This rests on 13 segments (2.3 km); one of
  the three segmentations alone shows 76%, so the size of the effect is very
  uncertain, but there is no evidence of a gain.
- **Confidence per region:** "high" holds everywhere (class right in 87–100%).
  "Low" and "medium" are clearly apart in Budapest (16% vs 88%) and
  Törökbálint (44% vs 62%), but not in Székesfehérvár (71% vs 66%) and
  Tapolca (72% vs 72%). In Budapest the low-confidence third of the road
  holds about five in six of the good/bad mistakes, so at least the weak
  spots are flagged. Per-region numbers rest on 13–64 segments.

### Image age

A "this image is old" penalty cannot be fitted from our data today
(`ml/segment_eval.py --age-check`, read-only on the local DB).
`street_view_images.capture_date` is filled for 17,442 of 17,607 frames (a
backfill was running on the day of writing). The frames are young: median
age 1.2 years, 12% older than 3 years, 2% older than 5.

- **Labels cannot tell.** A label describes the image, not today's road, so
  the labelled set says nothing about how a road changes after capture,
  whatever the capture dates are.
- **Repeat captures are the right evidence, but too thin.** 342 pairs of
  captures of the same spot (within 15 m, same street direction) on different
  dates exist. The model's class differs by ≥ 1 in 39% of the pairs less than
  a year apart, 31% at 1–2 years, 38% at 2–4 years and 44% beyond 4 years
  (103 pairs); the mean drift (later − earlier) is 0.00, −0.03, +0.05 and
  +0.11 class. Pairs taken months apart already disagree almost as often as
  pairs taken years apart, so no age effect can be measured.

Until labelled spots are re-collected after a known time, age can only be a
product rule: show the capture date, and if a penalty is wanted apply it only
beyond ~5 years (2% of the frames). It should not be a term of the measured
confidence.

### Verdict and recipe

**Aggregate to ~200 m segments with the median frame score.** 200 m is where
the gain over a single frame becomes clearly measurable and where it
flattens; the median is as good as any other sensible aggregator and is the
one that still protects against a junk frame when a segment has only three.
`ml/segment_recipe.json`:

```json
{
  "version": 1,
  "segment_length_m": 200,
  "aggregator": "median_score",
  "trim_fraction": 0.0,
  "thresholds": [1.577, 2.496, 3.052],
  "p_bad_threshold": 0.5,
  "min_images": 2,
  "recommended_frame_spacing_m": 30,
  "sampling": {"base_spacing_m": 50, "dense_spacing_m": 30, "densify_if": ["low_confidence"], "single_pass_spacing_m": 30},
  "confidence": {"n_ref": 0.5, "spread_ref": 2.0, "margin_ref": 0.6, "high": 0.8, "medium": 0.55},
  "integer_class_fallback": {"aggregator": "mean_class", "thresholds": [1.511, 2.52, 3.207]}
}
```

How the backend should read it:

1. **Input** is the continuous frame score (`analysis_metadata.dino_score`),
   not the integer class. Segment score = median of the frame scores. The
   whole recipe works on the model's native scale (1 = excellent … 4 = poor,
   higher score = worse road); if the displayed scale is ever flipped or
   renamed, convert *after* applying the cut-points.
2. **Class** = 1 + the number of `thresholds` that are ≤ the segment score.
   The cut-points were tuned on all spatial out-of-fold segments (the 3
   segmentations pooled). They differ from the single-frame cut-points in the
   artifact and must not be swapped with them.
3. **Confidence** uses n, the IQR of the frame scores (quartiles with linear
   interpolation, 0 for a single frame) and the margin, then the two level
   thresholds.
4. **`min_images`**: with one frame the class is right in 64% instead of 71%
   and there is no spread; show such segments as "low" or not at all.
5. **`p_bad_threshold`** (optional good/bad flag): mean `dino_p_bad` ≥ 0.5,
   tuned through the live artifact's calibrator. In the nested measurement
   the mean-P(bad) flag reaches 91.6% good/bad accuracy against 89.4% for
   "class ≥ 3". The two can disagree on a segment, so use one of them
   consistently.
6. **`integer_class_fallback`**: when this was measured only 3,346 of the
   17,607 frames in the local DB stored `dino_score` (a re-score was under
   way); the rest had just the integer `dino_rqi_score`. For those,
   the mean of the integer classes with its own cut-points is as good for the
   class (QWK 0.842 / MAE 0.295 at 200 m), but the margin-based confidence is
   not calibrated for it. Backfilling `dino_score` is the proper fix.
7. **`sampling`**: collect a frame every `base_spacing_m`; compute the
   segments and their confidence; on segments whose confidence is "low"
   (< `confidence.medium`) add frames every `dense_spacing_m` and recompute.
   With a single pass, use `single_pass_spacing_m`
   (= `recommended_frame_spacing_m`).
8. Where the cuts fall does not matter (QWK ±0.015 between segmentations),
   so the backend can segment along routes or streets as is convenient;
   chains should break at gaps > 40 m and at sharp turns.

Other lengths, same recipe (use these if a finer map is wanted):

| length | cut-points | n_ref / spread_ref / margin_ref | QWK / MAE | high: share, P(correct) | medium | low |
|---|---|---|---|---|---|---|
| 100 m | 1.48, 2.39, 2.98 | 0.5 / 1.0 / 0.6 | 0.819 / 0.328 | 13%, 0.92 | 56%, 0.69 | 31%, 0.56 |
| 150 m | 1.58, 2.50, 3.05 | 0.5 / 2.0 / 0.7 | 0.834 / 0.320 | 15%, 0.99 | 59%, 0.65 | 26%, 0.59 |
| **200 m** | 1.58, 2.50, 3.05 | 0.5 / 2.0 / 0.6 | 0.843 / 0.292 | 20%, 0.93 | 58%, 0.70 | 22%, 0.53 |

### What it means for the map

- **Colour segments, not frames.** A 200 m segment's class is right 7 times
  out of 10 and never off by more than one; its good/bad call is right 9
  times out of 10. Frames can still be shown on zoom-in, but they are not
  more accurate than their segment.
- **Show three confidence levels.** One fifth of the road is "high" (class
  right in 93%, good/bad never wrong in our data). A quarter is "low": there
  the class is little better than a coin flip between two neighbours and the
  good/bad call is wrong one time in four, so it should look uncertain.
- **Collect sparsely, then look again where unsure.** A frame every 50 m and
  a second pass at 30 m on low-confidence segments gives the same segment
  quality with a quarter of the frames (uniform 30 m: a third). Single
  defects are a separate layer and need dense frames where they matter.
- **What aggregation cannot fix:** a whole stretch judged wrongly, a region
  the model reads differently (a constant offset around Tapolca, the good|bad
  decision in Budapest), and old images. Those need more varied labels and a
  holdout region (the Era 6 recommendations), not more frames of the same
  road. In inner Budapest the segment colours deserve the least trust.

Limits of this measurement: 19.5 km of road in 35 cells and 4 regions, so
the intervals are wide (QWK ±0.08). The segment truth is the median of one
annotator's frame labels. The segment length, the aggregator and the two
level thresholds were chosen after looking at these tables (the parameters
themselves were checked across folds), so expect slightly lower numbers on
new roads.

Reproduce:

```bash
.venv/bin/python ml/segment_eval.py                 # all tables above (~5 min)
.venv/bin/python ml/segment_eval.py --write-recipe  # also rewrites ml/segment_recipe.json
.venv/bin/python ml/segment_eval.py --length 100    # confidence / spacing / regions for another length
.venv/bin/python ml/segment_eval.py --age-check     # optional: image age in the local DB
```

---

## Mi él most, és mi halott?

| komponens | állapot | szerep |
|---|---|---|
| **v2 RQI-motor** (`ml/cache/rqi_model.joblib` + `dino_service.py`) | ✅ ÉLES | a térképen látható RQI + P(rossz) |
| YOLO hibadetektálás (`road_analyzer.py`, `inference.py`) | ✅ él | hibapoligonok a részletkártyán, annotálás |
| v1 Ridge-recept (`ml/legacy/`: `extract_features.py`, `train.py`, `save_model.py`) | 📦 referencia | a v2 szkriptek váltották le |
| DINO v1 fej + webes tanítás (`train_dino_head.py`, DinoTraining oldalak) | ❌ zsákutca | az eredményét már semmi nem tölti be |
| FastSAM előfeldolgozás (`preprocessing.py`, `FastSAM-s.pt`) | ⚠️ félholt | csak YOLO-tanítóadat-export + annotáló-előnézet |
| Heurisztika | ❌ halott | csak a settings-szemét maradt belőle |

*(A halott/félholt részek rendbetételét a [IMPROVEMENT_PLAN.md](IMPROVEMENT_PLAN.md) fedi.)*

## Általános tanulságok

1. **Kis adatnál a recept számít, nem a modellméret** — ugyanaz a DINOv2
   backbone QWK 0.83-at és használhatatlant is tudott produkálni, a tanítási
   protokolltól függően; a 2× nagyobb base pedig semmit nem adott hozzá.
2. **A kiértékelési protokoll az igazi termék:** fix seed-ű, rétegzett
   keresztvalidáció + azonos fold-ok nélkül a "javulás" gyakran csak zaj.
   Minden jövőbeli modellnek ugyanezen a mérésen kell vernie a mostanit.
   **És a fold-oknak térben kell elválniuk:** sorozatfelvételeknél a véletlen
   CV a helyet méri, nem a képességet. Egy csak GPS-t látó k-NN is QWK
   0.88-at ért el rajta.
3. **Az adat olcsóbb, mint az architektúra:** a +665 visszaszerzett kép többet
   ért, mint bármelyik architektúra-trükk.
4. **Sorrendi skálát sorrendként kezelj** (regresszió + hangolt vágópontok),
   ne független osztályokként.
5. **A kalibrált valószínűség többet ér, mint a nyers osztályzat** — a
   "92%-ban helyes jó/rossz döntés + megmondja, mennyire biztos" a termék
   valódi ígérete.

---

## Era 8 — Higher-resolution road features (2026-11-26)

**Question.** The v2 recipe passes the 600×400 frame through the HF DINOv2
processor: resize the short side to 256 (→ 384×256), then centre-crop 224×224.
The backbone sees the frame at **0.64× scale**, without the outer 21% on each
side and the bottom 6%. Is crack-scale pavement texture in the road region
(the lower ~50%) being lost, and would higher-resolution road-region features
beat the champion? A second question: does the project's YOLO damage
segmenter add evidence on top of DINO?

**TL;DR**

- **The hypothesis is refuted.** Road-only DINOv2 features get *worse* as
  resolution rises: on the bottom half of the frame, mean+std pooling, SVR,
  QWK goes 0.781 (0.5× scale) → 0.761 (1.0×) → 0.767 (1.5×) → 0.745 (2×,
  centre of the lane). Every road-only model is at or below the champion
  (0.774). Frozen DINOv2 + a small head gets its signal from the scene, not
  from crack-scale texture.
- **Adding a second view to the champion helps a little, at any
  resolution.** The best of 170 grid cells reach ΔQWK ≈ +0.02 on the official
  grid. On 6 shifted grids they shrink to +0.006…+0.013. Low-resolution
  controls gain as much as their high-resolution twins: the full frame at
  336×224 gives +0.020 [+0.005, +0.036], the same frame at 588×392 gives
  +0.021 [+0.003, +0.039]. The gain comes from the wider field of view (no
  centre-crop), std/texture pooling and score averaging, not from resolution.
- **YOLO damage evidence adds nothing.** YOLO-only features reach QWK
  0.54–0.62. Stacked with the champion the best result is +0.004 [−0.005,
  +0.016].
- **One candidate formally qualifies:** dinov2-base cls+patch @224 + the
  full frame at 588×392, mean and std of block-8 tokens over the road half,
  SVR. On the official grid it has ΔQWK +0.021 [+0.001, +0.040]; on the
  shifted grids its CI is above 0 in 4 of 6 (the rule was fixed before the
  check). The gate gives **PASS** and "measurably better: YES": QWK 0.796 /
  MAE 0.382 / AUC 0.940. It is saved as `ml/cache/rqi_model_candidate.joblib`,
  and `dino_service` can run it (backend parity verified).
- **Recommendation: do not promote yet.** The lead decides. The margin is the
  smallest the rule allows, and its shift-mean (+0.013) equals that of
  variants that failed (2/6). It costs about **11× more inference** (186 vs
  17 ms/frame → ~54 vs ~5 min per 17.6k frames on MPS), and class-3 recall
  drops 0.68 → 0.57. Re-measure on the planned holdout region first.
- Not gated, but consistent across many two-view variants: MAE −0.02…−0.05,
  class-2 recall 0.43 → 0.45–0.55, Budapest bad-road AUC 0.78 → 0.80–0.85.

### Setup

Same protocol as the gate (`ml/spatial_cv.py`): 1903 images, 35 cells of
1 km, StratifiedGroupKFold 5, seed 42, nested cut-points. Every candidate is
paired against the champion on identical folds (cell-bootstrap ΔQWK 95% CI).
The harness reproduces the champion exactly (0.774 / 0.405 / 0.934, class-2
recall 0.43, Budapest QWK 0.404 / AUC 0.776). **Decision rule, fixed before
the shift check:** "measurably better" = ΔQWK CI > 0 on the official grid
**and** on at least 4 of 6 shifted grids.

Views (`ml/extract_features_hires.py`). Preprocessing is a PIL crop + BICUBIC
resize + ImageNet mean/std, with no HF processor and no centre-crop.
Throughput is DINOv2-small on MPS, measured while other jobs shared the
machine, so treat it as a lower bound.

| view | crop (frame fractions) | input | scale vs native | tokens | small, img/s | 17.6k frames |
|---|---|---|---|---|---|---|
| champion | centre 58% × 88% | 224×224 | 0.64 | 256 | – | – |
| `road50lo` | bottom 50% | 308×98 | 0.51 | 154 | 109 | 3 min |
| `road50` | bottom 50% | 588×196 | 0.98 | 588 | 26 | 11 min |
| `road50x15` | bottom 50% | 882×294 | 1.47 | 1323 | 3–6* | 50–90 min* |
| `roadc2x` | x 0.2–0.8, y 0.55–1 | 714×350 | 1.98 | 1275 | 11 | 27 min |
| `fulllo` | whole frame | 336×224 | 0.56 | 384 | 31 | 9 min |
| `full` | whole frame | 588×392 | 0.98 | 1176 | 9 | 33 min |

\*measured under heavy load (load average ~35). dinov2-base `road50`: 12 img/s.

Pooled per view: CLS, road-region patch mean / std / GeM(p=3), lower-centre
patch mean (the lane ahead, no logo corners), a 2×3 spatial pyramid, and
mean+std of block-8 tokens ("mid"). Heads: the champion SVR on the
concatenation (`svr`), and `svravg`, which averages a champion-feature SVR
with an SVR on the extra block (score-level ensemble). Ridge and RBF on large
concatenations were consistently worse.

### Results (official grid, paired vs champion)

| candidate | head | QWK | MAE | AUC | class-2 recall | Budapest QWK / AUC | ΔQWK [95% CI] |
|---|---|---|---|---|---|---|---|
| **champion** (cls+patch @224, small) | svr | 0.774 | 0.405 | 0.934 | 0.43 | 0.404 / 0.776 | – |
| *Resolution sweep, road-only (bottom half, mean+std):* | | | | | | | |
| road50lo (0.5×) | svr | 0.781 | 0.405 | 0.927 | 0.41 | 0.434 / 0.770 | +0.006 [−0.026, +0.035] |
| road50 (1.0×) | svr | 0.761 | 0.445 | 0.927 | 0.37 | 0.426 / 0.771 | −0.014 [−0.058, +0.025] |
| road50x15 (1.5×) | svr | 0.767 | 0.426 | 0.927 | 0.41 | 0.395 / 0.776 | −0.007 [−0.036, +0.019] |
| roadc2x (2×, lane centre) | svr | 0.745 | 0.437 | 0.918 | 0.45 | 0.418 / 0.757 | −0.029 [−0.073, +0.004] |
| *Champion + second view (score average):* | | | | | | | |
| + patch_crop @224 (existing v2 cache, control) | svravg | 0.786 | 0.410 | 0.939 | 0.40 | 0.448 / 0.791 | +0.012 [−0.014, +0.036] |
| + road50lo mean+std | svravg | 0.795 | 0.374 | 0.937 | 0.46 | 0.377 / 0.808 | +0.021 [−0.001, +0.043] |
| + road50 mean+std | svravg | 0.789 | 0.390 | 0.937 | 0.44 | 0.426 / 0.803 | +0.015 [−0.008, +0.039] |
| + road50 mid | svravg | 0.794 | 0.374 | 0.940 | 0.49 | 0.514 / 0.830 | +0.019 [+0.002, +0.036] |
| + fulllo mean+std | svravg | 0.795 | 0.378 | 0.940 | 0.48 | 0.477 / 0.815 | +0.020 [+0.005, +0.036] |
| + full mean+std | svravg | 0.795 | 0.379 | 0.941 | 0.48 | 0.451 / 0.812 | +0.021 [+0.003, +0.039] |
| *Single pass replacing the 224 view:* | | | | | | | |
| full cls+allmean (= v2 recipe at 588×392, no crop) | svr | 0.784 | 0.379 | 0.931 | 0.51 | 0.367 / 0.731 | +0.009 [−0.016, +0.035] |
| full cls+allmean+roadmean | svr | 0.799 | 0.353 | 0.937 | 0.55 | 0.398 / 0.785 | +0.025 [−0.005, +0.055] |
| fulllo cls+allmean+roadmean (control) | svr | 0.777 | 0.390 | 0.936 | 0.51 | 0.392 / 0.771 | +0.003 [−0.010, +0.017] |
| *dinov2-base:* | | | | | | | |
| base champion recipe | svr | 0.779 | 0.407 | 0.929 | 0.42 | 0.147 / 0.730 | +0.005 [−0.026, +0.029] |
| base road50 cls+mean | svr | 0.780 | 0.399 | 0.926 | 0.41 | 0.334 / 0.721 | +0.006 [−0.026, +0.035] |
| base champ + road50 mid | svr | 0.799 | 0.374 | 0.939 | 0.46 | 0.480 / 0.813 | +0.025 [+0.005, +0.045] |
| base champ + road50 GeM | svr | 0.798 | 0.372 | 0.934 | 0.48 | 0.429 / 0.784 | +0.023 [+0.003, +0.042] |
| base champ + full mid | svr | 0.796 | 0.382 | 0.940 | 0.46 | 0.531 / 0.826 | +0.021 [+0.001, +0.040] |
| base full mean+std (single pass) | svr | 0.797 | 0.375 | 0.940 | 0.47 | 0.448 / 0.823 | +0.023 [−0.006, +0.062] |
| *YOLO damage evidence (experiment 2):* | | | | | | | |
| YOLO features only (240) | svr | 0.611 | 0.569 | 0.808 | 0.50 | 0.296 / 0.673 | −0.164 [−0.224, −0.089] |
| champion + YOLO "any damage" (24) | svr | 0.779 | 0.402 | 0.936 | 0.43 | 0.466 / 0.778 | +0.004 [−0.005, +0.016] |
| champion + all YOLO (240) | svravg | 0.768 | 0.412 | 0.917 | 0.49 | 0.392 / 0.731 | −0.006 [−0.047, +0.040] |

All 170 cells are in `ml/cache/experiments_hires_*.csv`. The ΔQWK median is
+0.007 and the maximum +0.025. The 7 cells with CI > 0 are expected from
multiple testing of strongly correlated cells.

### Winner's-curse check (6 shifted grids, paired ΔQWK vs champion)

| candidate | ΔQWK per shifted grid | mean | CI > 0 |
|---|---|---|---|
| champ + road50 mid (svravg) | +0.014 +0.000 +0.001 +0.019 +0.007 +0.008 | +0.008 | 2/6 |
| champ + road50lo mean+std (svravg) | +0.012 +0.000 +0.000 +0.020 +0.000 +0.004 | +0.006 | 1/6 |
| champ + full mean (svravg) | +0.008 +0.014 +0.004 +0.009 +0.006 +0.009 | +0.008 | 0/6 |
| champ + full mean+std (svravg) | +0.015 +0.010 −0.005 +0.010 +0.008 +0.008 | +0.008 | 1/6 |
| champ + fulllo mean+std (svravg) | +0.013 +0.015 −0.003 +0.014 +0.014 +0.003 | +0.009 | 2/6 |
| full cls+allmean+roadmean (svr, single pass) | +0.013 +0.015 −0.001 +0.026 +0.014 +0.000 | +0.011 | 1/6 |
| base champ + road50 GeM (svr) | +0.016 +0.011 +0.005 +0.014 +0.009 +0.009 | +0.011 | 1/6 |
| base champ + road50 mid (svr) | +0.017 +0.019 +0.002 +0.015 +0.007 +0.011 | +0.012 | 1/6 |
| base full mean+std (svr, single pass) | +0.016 +0.018 −0.002 +0.016 +0.012 +0.020 | +0.013 | 2/6 |
| **base champ + full mid (svr)** | +0.017 +0.019 −0.001 +0.012 +0.023 +0.007 | +0.013 | **4/6** |

The deltas are almost all positive, but they are about +0.01. Only base
champ + full mid clears the pre-set rule (CI > 0 on at least 4 of 6 grids),
and its effect size is the same as its neighbours'. Feature engineering on
frozen DINOv2 is still capped by the data: it moves QWK by about +0.01, far
less than the ±0.07 CI of a single number.

### The candidate artifact

`ml/cache/rqi_model_candidate.joblib` (gitignored; rebuild with the command
below). Recipe `cls+patch+full_mid`, backbone `facebook/dinov2-base`, head
StandardScaler + SVR-RBF (C=1, eps=0.05), 3072 features. The
`feature_recipe` carries a new `hires_views` spec:
`{"full": {"box": [0,0,1,1], "size": [588,392], "mid_layer": 8, "road_y": 0.5}}`
with keys `full_midmean`, `full_midstd`. The backend interprets it through
the new torch-free `backend/app/services/hires_views.py`, with unit tests in
`backend/tests/test_hires_views.py`. `ml/check_backend_parity.py` confirms
that `dino_service` rebuilds the training features exactly (max relative
diff 1.8e-7, score Δ 0.0000 on 40 frames). The champion passes the same
check.

| (spatial CV, official grid) | champion | candidate |
|---|---|---|
| QWK | 0.774 | **0.796** (Δ +0.021 [+0.001, +0.040]) |
| MAE | 0.405 | 0.382 (Δ −0.023 [−0.056, +0.013]) |
| bad-road AUC | 0.934 | 0.940 (Δ +0.006 [+0.000, +0.014]) |
| exact | 0.610 | 0.630 |
| recall 1 / 2 / 3 / 4 | 0.83 / 0.43 / 0.68 / 0.60 | 0.87 / 0.46 / **0.57** / 0.74 |
| Budapest QWK / MAE / AUC | 0.404 / 0.397 / 0.776 | 0.531 / 0.306 / 0.826 |
| inference (MPS, batch 1) | 17 ms/frame | 186 ms/frame |

Promoting it would mean replacing `rqi_model.joblib` and re-scoring the map.
Only `dino_service` changes in code, and that change is already in place and
backward compatible: classic recipes take the same code path as before.

### YOLO sanity check (experiment 2)

The weights loaded are the production setting `yolo_model` =
`data/models/yolov8m-seg-best-20260105.pt` (9 classes: 6 damage types plus
shadow/manhole/marking), at production threshold 0.15. This owner-trained
model's quality had never been measured. Inside the production ROI trapezoid,
on the 1903 labelled frames:

| class | fires on | mean area % for RQI 1 / 2 / 3 / 4 | Spearman ρ vs RQI |
|---|---|---|---|
| long_crack | 5.9% | 0.07 / 0.06 / 0.06 / 0.00 | −0.04 (no signal) |
| trans_crack | 12.6% | 0.04 / 0.17 / 0.23 / 0.12 | +0.13 |
| alligator_crack | 12.2% | 0.08 / 0.41 / 0.99 / 1.12 | +0.22 |
| pothole | 2.7% | 0.00 / 0.01 / 0.04 / 0.13 | +0.20 |
| patch | 9.6% | 0.00 / 0.13 / 0.56 / 1.96 | +0.32 |
| degradation | 16.0% | 0.01 / 0.41 / 1.91 / 9.17 | +0.48 |
| any damage | 42.1% | 0.20 / 1.17 / 3.73 / 12.16 | +0.54 |

Frames with any damage detection, by true class: RQI 1 14%, RQI 2 38%,
RQI 3 68%, RQI 4 84%. The signal is real and monotone, but it comes mostly
from the coarse "degradation"/"patch" masks. Crack classes are weak or noisy.
A visual check (one frame per class) matches: the RQI 1 frame is clean, and
the RQI 4 frame gets a plausible whole-lane degradation mask. On the RQI 2
motorway, lane-marking edges and joints are labelled as transverse/alligator
cracks. On the RQI 3 frame there are tiny distant "patch" boxes plus a
"shadow". Everything YOLO knows is already in the DINO features: on its own it
reaches QWK 0.54–0.62, and stacked with the champion the best is +0.004
(n.s.). No tuning was done around it.

### Verdict and what it means

1. **Resolution is not the bottleneck.** At native or upsampled resolution
   the road crop carries no more usable signal for a frozen backbone + small
   head, and standalone it carries less. High-resolution passes help only as
   a wider, uncropped second view, and a 336×224 pass does that just as well.
2. **One formal pass, not a clear win.** The base + full-mid candidate
   clears the gate and the pre-set shift rule by the smallest margin. The
   decision to promote belongs to the lead. My recommendation is to keep the
   v2 champion live and re-measure the candidate, plus the cheap
   "champion + fulllo mean+std" score average (~+0.009 across shifts, one
   extra 31 img/s pass), on the independent holdout region once it is
   labelled.
3. **YOLO stays where it is** (defect polygons on the detail card). Its
   damage areas do not improve the RQI score.

Reproduce (all caches land in `ml/cache/`, gitignored):

```bash
PY=/Users/i/Dev/smooth-route/.venv/bin/python
for v in road50lo road50 road50x15 roadc2x fulllo full; do $PY ml/extract_features_hires.py --backbone small --view $v; done
for v in road50 full; do $PY ml/extract_features_hires.py --backbone base --view $v; done
$PY ml/extract_yolo_features.py                      # -> yolo_feats.npz (~6 min)
$PY ml/experiments_hires.py --heads svr,svravg       # full grid (~2 h on CPU)
$PY ml/experiments_hires.py --only yolo --heads svr,svravg,ridge
$PY ml/experiments_hires.py --views road50,road50lo,full,fulllo --backbones small --shifts 6 \
  --pairs "champ+full mean+std@svravg;champ+fulllo mean+std@svravg;champ+road50 mid@svravg;champ+full mean@svravg;full cls+allmean+roadmean@svr;champ+road50lo mean+std@svravg"
$PY ml/experiments_hires.py --views road50,full --backbones small,base --shifts 6 \
  --pairs "[base] champ+road50 mid@svr;[base] champ+road50 gem@svr;[base] champ+full mid@svr;[base] full mean+std@svr"
# candidate artifact, gate, backend parity:
$PY ml/save_model_v2.py --recipe cls+patch+full_mid --backbone base --out rqi_model_candidate.joblib
$PY ml/evaluate_artifact.py ml/cache/rqi_model_candidate.joblib   # PASS, measurably better: YES
$PY ml/check_backend_parity.py ml/cache/rqi_model_candidate.joblib

## Era 9 — VLM attributes as features (2026-11-26)

> **TL;DR:** Fable (Claude VLM) subagents described all 1903 labelled frames
> with 15 fixed, structured pavement attributes. Fed to a ridge stacker **next
> to the champion's score**, they give the first challenger that is
> **measurably better** on the official spatial CV: **QWK 0.805 / MAE 0.344 /
> bad-AUC 0.940** vs 0.774 / 0.405 / 0.934. ΔQWK is +0.031 [+0.006, +0.056],
> positive on all 5 shifted grids and with its CI above 0 on 4 of 5. Class-2
> recall rises from 0.43 to 0.56. Most of the gain is on cracked motorways,
> rural lanes and dappled shadow. **Budapest does not improve** (QWK 0.40 →
> 0.42). The gain **needs a VLM call per frame**: distilling the attributes
> into DINO heads keeps none of it. The gate PASSes and the candidate is
> saved as `ml/cache/rqi_model_vlm_candidate.joblib`, but it is **not
> promoted**, because the backend cannot produce the attributes.

### Setup

- **Schema** (`ml/vlm_attribute_prompt.md`, the same text for every worker,
  one JSON line per frame): road_visible, road_type, surface, cracks
  (none … alligator_extensive), patches, potholes, ravelling, edge_damage,
  rutting, markings, lighting, wet, obstruction_pct, rqi_guess (pilot
  rubric), confidence, plus a ≤12-word note. Workers judge the camera's own
  road, mainly the lower 40% of the frame. `ml/vlm_attributes.py` encodes
  these into 30 columns: ordinal severities plus one-hot levels, with levels
  under 1% dropped (`MODEL_COLUMNS`).
- **Blinding:** frames were hard-linked under random ids into 16 shuffled
  batches of about 118. Each worker could open only its own images, the 12
  calibration anchors (`anchor_<RQI>_<k>.jpg`, as in the pilot) and its own
  output file. Outputs are in `data/vlm/attributes/out/*.jsonl` (resumable)
  and the merge is in `ml/cache/vlm_attributes.csv` (committed).
- **Anchor leakage, found and fixed during the run.** Consecutive frames
  about 10 m apart are often the *same panorama*: the 1903 frames contain 70
  pixel-identical pairs. One worker recognised an anchor's twin in its batch.
  So all 100 frames within 50 m of an anchor, plus the anchors themselves,
  were re-rated by a worker that saw no anchors (batch b00), and that row is
  the one used. The check shows why this mattered. On those 100 frames, the
  anchored rating matched the expert 61% of the time (QWK 0.78), the
  anchor-free rating only 41% (QWK 0.54). Part of the gap is calibration:
  anchor-free guesses run about 0.3 lower.
- **Consistency:** two independent workers on the same 30 pilot frames agreed
  on 83–100% of attribute values, and their rqi_guess values agreed at QWK
  0.85. A pilot worker and a full-run worker on the same frames agreed on
  0.73 (cracks, patches) to 1.00.
- **Cost:** 19 Fable workers, 2.7 M subagent tokens (~1.26 k per frame
  including the anchors), about 6.5 min per 118-frame worker, about 25 min
  wall-clock in two waves of 8.
- **What the VLM saw:** motorway 764, rural road 402, urban main 378,
  residential 234, rural lane 123. Surface was asphalt in 1899 of 1903 frames,
  so **no cobblestone in this dataset**. Dappled shadow 186, wet 7. The
  rqi_guess distribution was 430 / 951 / 496 / 26 against the human
  540 / 780 / 381 / 202, so like the pilot it under-calls 4.

### Results (official spatial CV, paired cell bootstrap vs the champion)

`ml/vlm_feature_eval.py`. Every stacker, blend weight and distillation head is
fit inside the training folds only. The champion score fed to a stacker is
inner-OOF, and the cut-points are nested.

| candidate | QWK | MAE | AUC | ΔQWK [95% CI] | Budapest QWK | class-2 recall |
|---|---|---|---|---|---|---|
| champion: DINO cls+patch → SVR | 0.774 | 0.405 | 0.934 | – | 0.404 | 0.43 |
| (0) VLM rqi_guess used as the label | 0.613 | 0.490 | 0.796 | −0.161 [−0.231, −0.093] | 0.262 | 0.67 |
| (a) attributes alone → ridge | 0.777 | 0.377 | 0.919 | +0.002 [−0.035, +0.039] | 0.291 | 0.52 |
| (a) attributes without rqi_guess → ridge | 0.774 | 0.377 | 0.918 | −0.001 [−0.039, +0.040] | 0.343 | 0.54 |
| (b) DINO + attributes (block ×5.1) → SVR | 0.797 | 0.362 | 0.933 | +0.022 [−0.004, +0.047] | 0.411 | 0.51 |
| (b) DINO + attributes → ordinal logit | 0.783 | 0.394 | 0.941 | +0.009 [−0.009, +0.028] | 0.520 | 0.47 |
| (c) champion score + attributes → ridge | 0.802 | 0.347 | 0.941 | **+0.028 [+0.005, +0.056]** | 0.417 | 0.54 |
| (c) champion score + attributes → HistGB | 0.797 | 0.345 | 0.940 | +0.023 [−0.004, +0.056] | 0.442 | 0.57 |
| (d) blend champion + rqi_guess (α ≈ 0.26) | 0.788 | 0.378 | 0.941 | +0.014 [−0.010, +0.038] | 0.454 | 0.52 |
| **(c) as gate artifact** (`StackedVLMHead`) | **0.805** | **0.344** | **0.940** | **+0.031 [+0.006, +0.056]** | 0.424 | 0.56 |

- **Robustness of the artifact head on 5 shifted 1 km grids:** ΔQWK +0.024,
  +0.033, +0.009, +0.022, +0.027, with the CI above 0 on 4 of 5; ΔMAE −0.03
  to −0.08, with the CI below 0 on 4 of 5; ΔAUC +0.001 to +0.008 (not
  significant). The evaluation-script stacker (c) gave ΔQWK +0.018, +0.033,
  −0.001, +0.013, +0.032. For comparison, Era 6's best challenger had its CI
  above 0 on 1 of 6 grids.
- **The 1–4 decision improves more than the good/bad decision.** AUC moves
  only +0.006. The candidate's confusion matrix gives recall
  0.83 / 0.56 / 0.63 / 0.70 for classes 1–4 (champion 0.83 / 0.43 / 0.67 /
  0.60).
- **Attributes alone match DINO** (QWK 0.777). That is an independent view
  with equal skill, but its errors correlate with the champion's, so only
  stacking helps. The VLM's own rqi_guess is a weak labeller (QWK 0.61), as
  in the pilot.

### Where the gain comes from (do the attributes explain the errors?)

Champion OOF error by VLM attribute, next to the stacked model's (official
folds; bias = predicted − true):

| subgroup | n | champion MAE / bias | stacked MAE / bias |
|---|---|---|---|
| motorway with cracks | 473 | 0.52 / −0.30 | 0.40 / −0.11 |
| many longitudinal cracks | 328 | 0.51 / −0.25 | 0.43 / +0.02 |
| many transverse cracks | 60 | 0.55 / −0.42 | 0.42 / +0.05 |
| dappled shadow | 186 | 0.49 / +0.04 | 0.39 / +0.15 |
| rural lane | 123 | 0.43 / −0.12 | 0.37 / −0.01 |
| residential street | 234 | 0.42 / +0.32 | 0.38 / +0.29 |
| urban main road | 378 | 0.44 / +0.09 | 0.44 / +0.10 |
| Budapest | 229 | 0.40 / +0.13 | 0.39 / +0.04 |
| human class 2 | 780 | 0.59 / −0.06 | 0.48 / +0.05 |
| human class 4 | 202 | 0.44 / −0.44 | 0.40 / −0.40 |

- **Sealed-crack motorways are the champion's biggest systematic miss.** The
  expert calls them 2; DINO sees a smooth motorway and says 1. The VLM's
  crack pattern fixes most of this. The stacker's standardised weights are
  champion score +0.42, patches +0.15, rural_lane +0.10, rqi_guess +0.09,
  motorway −0.07, ravelling +0.07.
- **Dappled shadow:** the champion's MAE on these frames is ~20% above
  average (0.49). The attributes bring it down to the champion's own
  normal-lighting level (0.39).
- **Cobblestone** cannot be tested here, because no frame has it.
- **Still unsolved:** residential streets are over-predicted (+0.29), and
  urban main roads and Budapest do not improve. Class 4 is still under-called,
  and the VLM shares that bias.

### Distillation (the production path without a VLM)

Ridge heads on DINO cls+patch, trained on the training fold's VLM attributes,
predict many attributes well. Spatial OOF r: road_type=motorway 0.87,
edge_damage 0.86, dappled shadow 0.82, rqi_guess 0.75, patches 0.74,
ravelling 0.73; fine crack patterns only 0.2–0.4. But **none of the gain
survives** when the predicted attributes replace the VLM ones:

| distilled variant (no VLM at inference) | QWK | MAE | ΔQWK [95% CI] |
|---|---|---|---|
| distilled attributes alone → ridge | 0.753 | 0.440 | −0.022 [−0.072, +0.023] |
| DINO + distilled attributes → SVR | 0.787 | 0.391 | +0.012 [−0.002, +0.028] |
| champion score + distilled → ridge / HistGB | 0.758 / 0.772 | 0.415 / 0.383 | −0.016 / −0.002 |
| blend champion + distilled rqi_guess | 0.783 | 0.396 | +0.009 [−0.008, +0.026] |
| *control:* DINO + ridge-distilled **human** label → SVR | 0.775 | 0.407 | +0.001 [−0.006, +0.007] |

The stacking gain goes from +0.028 to between −0.016 and −0.002, so **0%
survives**. The best distilled variant (+0.012, not significant) is barely
above the control, which pushes the human label through the same ridge
channel. The useful VLM information is the part that DINO features do not
encode. A function of DINO cannot carry it, however well it imitates the
attributes. A distilled student would need a stronger image model and many
more VLM-rated frames (for example the ~15 k unlabelled frames under
`data/images`). That has not been tested.

### Label audit (by-product, no labels changed)

`data/vlm/label_audit.csv` has 60 rows for the owner to re-check:

- 5 frames where the VLM and the model are both ≥ 2 off the human label.
- 12 where a high-confidence VLM and the model agree against the human. These
  are mostly smooth motorway frames labelled 2 that both call 1.
- **9 pairs of pixel-identical frames (same panorama ~10 m apart) with
  different human labels** (18 frames). These are the cheapest fixes, and
  label noise the CV counts as model error.
- 25 rows to fill the list: medium-confidence VLM = model ≠ human, ranked by
  how far the model's score is from the label.

### Verdict and production implication

- **Measurably better, gate PASS:**
  `evaluate_artifact.py ml/cache/rqi_model_vlm_candidate.joblib` → PASS,
  "measurably better: YES". This is the first such result on the spatial
  protocol. **Not promoted:** `rqi_model.joblib` is unchanged, and
  `dino_service` cannot build the `vlm` key of the `cls+patch+vlm` recipe.
- **What inference would need:**
  1. For each new frame, one VLM request with `ml/vlm_attribute_prompt.md`
     plus the 12 anchor images (a cacheable prefix) and the frame.
  2. Validate the JSON (`vlm_attributes.validate`) and encode it
     (`MODEL_COLUMNS`).
  3. Call `pipeline.predict` on `[cls+patch | attributes]` (head
     `ml/vlm_heads.py`, which must be importable).
  4. Fall back to the champion when the VLM is unavailable, and cache
     results per `pano_id`, since neighbouring frames often share a
     panorama.

  The cost is about 1.3 k tokens per frame. The attributes come from one
  model and one prompt, so changing either means re-rating the training set.
- **Cheaper options worth testing next:**
  - Run the VLM only on frames where the champion is unsure (P(bad) near
    0.5, the 1|2 and 2|3 bands).
  - Run it on 1–2 frames per 100–200 m segment.
  - Use the VLM offline to rate unlabelled frames for a stronger student
    (the open distillation question above).
  - Average two VLM passes per frame to cut rater noise (retest agreement on
    cracks and patches is only ~0.75).

Reproduce:

```bash
.venv/bin/python ml/vlm_attributes.py prepare        # blinded batches + prompts
.venv/bin/python ml/vlm_attributes.py anchor_free    # anchor twins -> anchor-free batch b00
# ... run one Fable worker per data/vlm/attributes/prompts/<batch>.md ...
.venv/bin/python ml/vlm_attributes.py merge          # -> ml/cache/vlm_attributes.csv
.venv/bin/python ml/vlm_attributes.py pilot          # A-vs-B consistency
.venv/bin/python ml/vlm_attributes.py anchor_check   # leakage + retest
.venv/bin/python ml/vlm_feature_eval.py              # table above + label audit
.venv/bin/python ml/vlm_feature_eval.py --shift "(c) champion score + attrs -> ridge" --grid 0
.venv/bin/python ml/save_model_v2.py --recipe cls+patch+vlm --head stack-vlm --out rqi_model_vlm_candidate.joblib
.venv/bin/python ml/evaluate_artifact.py ml/cache/rqi_model_vlm_candidate.joblib
```
