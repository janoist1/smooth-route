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
| 5 | használhatatlan *(a gyakorlatban nincs elég példa → a modell 1–4-et ad)* |

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
