# Fogalomtár — mit jelentenek a szakszavak?

*Közérthető magyarázatok ahhoz, amit a modellről és a mérésekről rendszeresen
olvasol. Nem kell ML-esnek lenned hozzá. Minden fogalomnál ott a **„Nálunk"**
sor a projekt konkrét példájával.*

> **A legrövidebb összefoglaló:** egy kép alapján a gép ad egy 1–5 jegyet az út
> minőségére. Hogy tudjuk, mennyire megbízható, elrejtünk előle képeket,
> megkérdezzük, majd összevetjük az emberi jeggyel. A lenti számok (QWK, MAE,
> AUC…) mind azt fejezik ki **más-más szemszögből, hogy mennyire talál a gép
> jegye az emberével**.

---

## 1. Az alapszókincs

**RQI (Road Quality Index)** — a mi 1–5 útminőségi skálánk. **1 = kiváló** (új,
sima aszfalt), 4 = rossz (kátyús, töredezett). Az 5-öst nem használjuk (túl kevés
példa). *Fontos: nálunk a kisebb szám a jobb út.*

**Címke / ground truth (magyarul: „helyes válasz")** — a kézzel adott jegy egy
képre. Ez az „igazság", amihez a gépet hasonlítjuk. Ha a címke rossz, a gép is
rosszat tanul — ezért fontos a következetes címkézés.
*Nálunk: 1917 kézzel bepontozott kép a `training_data` táblában.*

**Modell** — a betanított „gép", ami egy képhez jegyet ad. Nálunk a fájlja az
`ml/cache/rqi_model.joblib`.

**Jellemző / feature** — a képből kinyert számok, amikből a modell dolgozik. Egy
kép a gépnek nem „kép", hanem több száz szám (pl. „mennyire textúrás a felület").
*Nálunk: a DINOv2 nevű háló 768 számmá alakít minden képet.*

---

## 2. A mérőszámok (mennyire jó a modell?)

Mindegyik ugyanazt a kérdést feszegeti — *„mennyire talál a gép jegye az
emberével?"* —, csak más nézőpontból. Ezért adunk meg többet: együtt festenek
teljes képet.

**Exact accuracy / pontos találat** — az esetek hány százalékában találja el
*pontosan* ugyanazt a jegyet, amit az ember adott.
*Nálunk: 81% — tízből nyolc képnél telibe talál.*

**±1 accuracy (plusz-mínusz egy pontosság)** — hányszor téved *legfeljebb egyet*
(pl. 3 helyett 2-t vagy 4-et mond). Egy ordinális skálán a szomszédos tévesztés
enyhe hiba; ez a szám azt mutatja, mennyire „nincs nagy melléfogás".
*Nálunk: 99.8% — nagy tévedés (pl. 1 helyett 4) gyakorlatilag sosincs.*

**MAE (Mean Absolute Error, átlagos abszolút hiba)** — átlagosan hány jeggyel
téved. Ha mindig telibe találna, 0 lenne; ha átlag fél jeggyel mellényúl, 0.5.
*Nálunk: 0.19 — átlagosan ötödannyit téved, mint egy egész jegy.*

**QWK (Quadratic Weighted Kappa, kvadratikusan súlyozott kappa)** — a
„fő" pontszámunk. Azt méri, mennyire **egyezik a gép jegye az emberével egy
sorrendi skálán**, és a nagy tévedést sokkal jobban bünteti, mint a kicsit (a
„kvadratikus" = a hibát négyzetre emeli). Ráadásul kiszűri a szerencsét: azt
nézi, mennyivel jobb a puszta találgatásnál. **0 = annyit ér, mint a találgatás,
1 = tökéletes egyezés.** 0.8 fölött már erős.
*Nálunk: 0.89 — közel az emberi címkéző önmagával való egyezéséhez (a
gyakorlati plafonhoz).*

**AUC (ROC AUC, a görbe alatti terület)** — egy *jó/rossz* (kétosztályos) döntés
minőségét méri: nálunk „rossz-e az út (RQI ≥ 3)?". Azt fejezi ki, mennyire jól
*rangsorol*: ha veszünk egy tényleg rossz és egy tényleg jó utat, milyen eséllyel
adja a rosszra a magasabb kockázatot. **0.5 = érme-feldobás, 1.0 = tökéletes.**
*Nálunk: 0.97 — kiváló jó/rossz szétválasztás.*

**Bad-road accuracy / jó-rossz döntés pontossága** — ugyanez, de nyers
százalékban: a jó/rossz besorolás hány százaléka helyes.
*Nálunk: 92%.*

**Confusion matrix / tévesztési mátrix** — táblázat, ami megmutatja, *mit mivel*
kever a gép (pl. „a 3-asok közül hányat mondott 2-nek"). Az átló a találatok; a
mellette lévő cellák a szomszédos tévesztések. Nálunk minden hiba az átló mellett
van, nincs 1↔4 keveredés.

**Baseline / naiv alapvonal** — a „buta" viszonyítási pont, amihez képest a modell
jóságát nézzük (pl. „mindig a leggyakoribb jegyet tippeli"). Ha a modell nem veri
meg a baseline-t, nem ér semmit.
*Nálunk: a naiv MAE 0.76 volt, a modellünké 0.19.*

---

## 3. Hogyan mérünk *becsületesen*? (a validáció)

A legnagyobb csapda, hogy a gép „bemagolja" a tanulóképeket, és a vizsgán csak
azokat ismeri fel. Ezért soha nem azon mérünk, amin tanítottunk.

**Train/test split (tanító/teszt szétválasztás)** — a képek egy részén tanítunk,
egy másik, *elrejtett* részén vizsgáztatunk. A vizsgapontszám a valódi.

**Overfitting / túltanulás** — amikor a gép a tanulóképeket magolja be általános
szabály helyett. Ilyenkor a tanuló-adaton szuper, új képen gyenge. Ez ellen véd
a rejtett teszthalmaz.

**Leakage / szivárgás** — amikor véletlenül „beszivárog" a válasz a tanulásba (pl.
ugyanaz a kép a tanuló- és a tesztkészletben is). Ilyenkor a pontszám hamisan
szép. Sokat teszünk azért, hogy ez ne történjen (ezért „szivárgásmentes").

**Cross-validation (CV) / keresztvalidáció** — nem *egy* szétvágásra bízzuk
magunkat (az lehet szerencse), hanem többre, és átlagolunk.

**5-fold CV (5-szörös keresztvalidáció)** — a képeket **5 egyenlő kupacra** osztjuk.
Ötször tanítunk: mindig 4 kupacon tanulunk, az 5.-en vizsgázunk — így *minden* kép
pontosan egyszer volt vizsgakép, de sosem a saját tanulásán. Az 5 eredményt
átlagoljuk. Ez sokkal megbízhatóbb, mint egyetlen szétvágás.
*(A „fold" = kupac/hajtás.)*

**Stratified / rétegzett** — a kupacok szétosztásánál ügyelünk, hogy mindegyikbe
arányosan kerüljön minden jegyből (ne legyen egy kupac csupa jó út). Így a vizsga
tisztességes.

**Out-of-fold (OOF) predikció** — minden képre az a jóslat, amit akkor kapott,
amikor éppen ő volt a *vizsgán* (nem a tanulásán). Ezekből számoljuk a becsületes
pontszámokat, és ezeken hangoljuk a vágópontokat és a valószínűség-kalibrációt.

**Nested / beágyazott CV** — CV a CV-ben. Ha nemcsak mérünk, hanem *hangolunk* is
(pl. a vágópontokat), a hangolást is elrejtett adaton kell csinálni, különben az
is szivárgás. A beágyazott CV pont ezt biztosítja — ezért „nested".

**Seed (véletlenmag)** — a véletlen műveletek (pl. a kupacokba osztás) egy fix
számból indulnak, hogy az eredmény **megismételhető** legyen. Nálunk `seed=42`.
Ugyanaz a seed = ugyanaz a szétvágás = összehasonlítható számok.

**Reprodukálhatóság** — hogy ugyanaz a kód ugyanazt az eredményt adja legközelebb
is. A fix seed és a rögzített recept ezt szolgálja.

---

## 4. A modell felépítése (miből áll a „gép"?)

A receptünk: **egy nagy, kész „látás-agy" + egy rátett kis döntéshozó.**

**Backbone (gerinc / „látás-agy")** — egy hatalmas, *előre* betanított háló, ami
általánosan „ért a képekhez" (élek, textúrák, formák). Nem mi tanítottuk, kész van;
mi csak *használjuk* jellemző-kinyerőként.
*Nálunk: **DINOv2-small** (a Meta AI modellje).*

**Frozen / fagyasztott** — a backbone-t *nem* tanítjuk tovább, „befagyasztjuk". Így
kevés adatból is működik, és gyors. Csak a rátett kis fejet tanítjuk.

**DINOv2 / CLIP** — konkrét előtanított hálók. A DINOv2 a jellemzőket adja; a CLIP-et
egy külön ellenőrzésre használjuk („ez a kép egyáltalán út-e?").

**CLS token / patch token** — a DINOv2 kétféle „kivonatot" ad a képről: a **CLS** az
egész kép összefoglalója, a **patch** tokenek a kis képrészletek (jó a
felület-textúrához, pl. repedések). Mi a kettő kombinációját használjuk.

**Head / fej** — a backbone-ra rátett *kicsi* modell, ami a jellemzőkből kiszámolja
a tényleges jegyet. Ezt tanítjuk a mi címkéinken.
*Nálunk: SVR-RBF.*

**Regresszió vs. osztályozás** — az *osztályozás* dobozokba sorol (1/2/3/4, ahol a
dobozok között „nincs sorrend"); a *regresszió* egy folytonos számot becsül (pl.
2.6), amit utána kerekítünk. Mi regressziót használunk, mert az RQI **sorrendi**:
a 4 rosszabb, mint a 3, ami rosszabb, mint a 2 — ezt a regresszió tiszteli, az
osztályozás eldobná.

**Ordinal / sorrendi skála** — olyan skála, ahol a számok *sorrendje* számít, de a
lépések nem feltétlenül egyenlők. Az RQI ilyen. Ezért használunk sorrend-tudatos
mérést (QWK) és regressziót.

**Ridge / SVR-RBF** — kétféle „fej" (döntéshozó). A **Ridge** egyszerű, egyenes
összefüggést tanul; az **SVR-RBF** görbült, összetettebb összefüggést is meg tud
fogni. Nálunk az SVR-RBF nyert (jobb QWK).

**StandardScaler / normalizálás** — a jellemzőket közös léptékre hozza (hogy egyik
szám se nyomja el a többit pusztán a nagysága miatt), mielőtt a fej megkapja őket.

**Pipeline** — a lépések összefűzése egy egységgé (nálunk: normalizálás → fej), hogy
mindig ugyanabban a sorrendben, ugyanúgy fussanak tanításnál és élesben is.

**Threshold / cut-point / vágópont** — a folytonos becslést (pl. 2.6) jeggyé kell
kerekíteni. Nem feltétlenül a felezőpontnál vágunk: **hangolt vágópontokkal** a
határokat oda tesszük, ahol a legjobb az egyezés. Nálunk pl. a 3|4 határ 3.18-nál
van (nem 3.5-nél), így jobban felismeri a rossz utakat.

**Kalibráció / P(bad) / izotonikus kalibráció** — a nyers becslést megbízható
**valószínűséggé** alakítja. A „P(bad)" = *„mekkora eséllyel rossz ez az út
(RQI ≥ 3)?"*. A *kalibrált* azt jelenti: ha a modell 70%-ot mond, akkor tényleg
kb. 10-ből 7 ilyen eset rossz út. Az „izotonikus" a matek módszer neve; a lényeg,
hogy a százalék valóban annyit érjen, amennyit mutat.
*Nálunk: ezt látod a pontkártyán „Rossz út valószínűsége" néven.*

**Reliability / megbízhatósági tábla** — megmutatja, hogy amikor a modell X-et mond,
a valóságban mi szokott lenni. Nálunk: ha 4-est mond, 80%-ban tényleg 4-es és
<1%-ban jó út — vagyis a „rossz" ítéletében meg lehet bízni.

**TTA (Test-Time Augmentation)** — trükk, amivel a képet többféleképp (pl.
tükrözve) is megmutatjuk a modellnek, és átlagolunk. Kipróbáltuk — nálunk nem
segített, ezért nincs bent. (Fontos elv: amit kipróbálunk és nem segít, azt is
megmérjük és kihagyjuk.)

**Class imbalance / osztály-egyensúlytalanság** — amikor egyes jegyekből sokkal
több példa van, mint másokból (nálunk a jó utakból). Ez torzíthat; ezért
szereztünk vissza 676 hiányzó (főleg jó-út) képet a kiegyensúlyozáshoz.

---

## 5. Gyakorlati / infrastruktúra

**Artifact** — a kész, elmentett modell egyetlen fájlban, mindennel, ami az
élesítéshez kell (a betanított fej, a recept, a vágópontok, a kalibrátor).
*Nálunk: `ml/cache/rqi_model.joblib`.*

**joblib** — a Python könyvtár, amivel a modellt fájlba mentjük/visszatöltjük.

**Promotion gate / élesítési kapu** — a szabály, hogy **új modell csak akkor mehet
élesbe, ha a fenti CV-mérésen eléri/veri a jelenlegit.** Nálunk ezt az
`ml/evaluate_artifact.py` automatikusan ellenőrzi (PASS/FAIL). Így nem tudunk
véletlenül rosszabb modellt kiadni.

**Backbone letöltés / MPS / CPU / CUDA** — hol fut a számítás. **MPS** = az Apple
gépek grafikus gyorsítása (nálunk a Mac ezt használja), **CUDA** = NVIDIA
kártyáké, **CPU** = sima processzor (lassabb). A modell mindegyiken fut.

**Epoch** — a *régi* (elvetett) tanításnál: egy teljes átfutás a tanulóadaton. A
mostani recept nem így tanul (a fej egyben illeszkedik), úgyhogy nálunk ez már
nem releváns — de régebbi doksikban/beállításokban még előbukkanhat.

**Inference / következtetés** — amikor a kész modellt *használjuk* egy új képre
(szemben a *tanítással*). A térképi pontozás inference.

---

## Kapcsolódó

- A modell történetét és a döntéseket közérthetően: [MODEL_EXPERIMENTS.md](MODEL_EXPERIMENTS.md)
- A pontos számok és a pipeline: [../ml/README.md](../ml/README.md)
- Ha valamit itt nem találsz és tőlem (az asszisztenstől) hallottad, szólj — bővítjük.
