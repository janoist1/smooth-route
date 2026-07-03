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

**Végeredmény (beágyazott, szivárgásmentes 5-fold CV, 1903 kép):**

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
nem okosabb modell.

---

## Mi él most, és mi halott?

| komponens | állapot | szerep |
|---|---|---|
| **v2 RQI-motor** (`ml/cache/rqi_model.joblib` + `dino_service.py`) | ✅ ÉLES | a térképen látható RQI + P(rossz) |
| YOLO hibadetektálás (`road_analyzer.py`, `inference.py`) | ✅ él | hibapoligonok a részletkártyán, annotálás |
| v1 Ridge-recept (`ml/extract_features.py`, `train.py`, `save_model.py`) | 📦 referencia | a v2 szkriptek váltották le |
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
3. **Az adat olcsóbb, mint az architektúra:** a +665 visszaszerzett kép többet
   ért, mint bármelyik architektúra-trükk.
4. **Sorrendi skálát sorrendként kezelj** (regresszió + hangolt vágópontok),
   ne független osztályokként.
5. **A kalibrált valószínűség többet ér, mint a nyers osztályzat** — a
   "92%-ban helyes jó/rossz döntés + megmondja, mennyire biztos" a termék
   valódi ígérete.
