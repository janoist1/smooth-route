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
```
