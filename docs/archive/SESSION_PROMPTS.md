# Session-indító promptok

*Másold be ezeket egy **friss** AI-session elején (Claude, GPT-5.5, Codex, bármi).
Mindegyik a router-mintára épül: az ágens az [AGENTS.md](../AGENTS.md) útválasztóból
csak a feladatához tartozó doksikat nyitja meg, így kicsi marad a kontextus.*

**Használat:** egy fázis / önálló munkaegység = egy session. A commit a
checkpoint. Ha a session tele van elintézett szálakkal vagy a modell ismételget,
zárd le és indíts újat a következő prompttal.

---

## 0. Univerzális sablon (bármely feladathoz)

```
A repó: /Users/i/Dev/smooth-route

Először olvasd el az AGENTS.md útválasztót, és nyisd meg CSAK a feladatodhoz
tartozó sort (a "NE olvasd" oszlopot is vedd figyelembe). Ne olvass be több
doksit, mint amennyi kell.

Feladat: <<IDE ÍRD A FELADATOT>>

Megkötések:
- Python: mindig a .venv/bin/python; ne hozz létre új venv-et.
- A tesztkapuknak zöldnek kell lenniük a végén:
    cd backend && ../.venv/bin/python -m pytest -q
    cd frontend && npm run typecheck && npm run lint && npm test
- RQI-modellt CSAK akkor élesíts, ha `.venv/bin/python ml/evaluate_artifact.py`
  PASS-t ad (QWK ≥ 0.889 / MAE ≤ 0.195 / bad-AUC ≥ 0.970).
- Fogalmak, ha kell: docs/GLOSSARY.md.
- A végén foglald össze a diffet és a tesztek eredményét. Commit/push CSAK
  explicit kérésre; commitolatlan munka esetén előbb tisztázd velem a kiindulást.
```

---

## E2 — DINOv3 backbone kipróbálása

```
A repó: /Users/i/Dev/smooth-route
Olvasd el az AGENTS.md útválasztót, majd CSAK az "RQI-modell / ml/" sort
(ml/README.md + docs/GLOSSARY.md). A frontendet NE nyisd meg.

Feladat: próbáld ki a DINOv3 backbone-t a v2 recept alternatívájaként.
1. Előfeltétel: a facebook/dinov3-* modell a Hugging Face-en licenc-kapus —
   ha 403-at kapsz, állj meg és szólj, hogy el kell fogadnom a licencet.
2. Illeszd be a DINOv3-at az ml/extract_features_v2.py backbone-opciói közé
   (a mostani "small"/"base" mintájára), és nyerd ki a jellemzőket.
3. Futtasd az ml/experiments.py rácsot és az ml/tune_svr.py hangolást az új
   jellemzőkön, ugyanazon a fix 5-fold CV-n (seed=42).
4. Döntés a KAPUVAL: csak akkor mentsd újra az ml/cache/rqi_model.joblib-et
   (ml/save_model_v2.py), ha az ml/evaluate_artifact.py PASS-t ad ÉS veri a
   jelenlegit. Ha nem ver, HAGYD a v2-t, és írd le a MODEL_EXPERIMENTS.md-be,
   mit mértél (számokkal) — a "kipróbáltuk, nem segített" is érték.

Megkötés: a backend/frontend tesztkapuk maradjanak zöldek; commit csak kérésre.
```

---

## E3 — P(rossz)-alapú térképszínezés + útvonal-minőségindex

```
A repó: /Users/i/Dev/smooth-route
Olvasd el az AGENTS.md útválasztót, majd CSAK a "Frontend UI" sort
(frontend/ARCHITECTURE.md). Az ml/-t NE nyisd meg. A backend már kiadja a
dinoPBad / dinoScore mezőket (ld. docs/API_SURFACE.md, csak ha kell).

Feladat: használd ki a már meglévő kalibrált P(rossz) értéket a térképen.
1. A pont-színezés a térképen tükrözze a P(rossz)-ot (nem csak a kerekített
   RQI-t) — pl. folytonos zöld→piros skála a dinoPBad alapján, amikor a DINO
   a megjelenítési forrás (rqi_display_source).
2. Adj egy útvonal-szintű összegzést: a kijelölt/betöltött pontokból egy
   egyszerű útvonal-minőségindex (pl. átlagos P(rossz), és a "rossz" pontok
   aránya), a meglévő UI-stílusban.
3. Tartsd tiszteletben a modulhatárokat (components csak hookon át; ld.
   ARCHITECTURE.md). A megjelenítési logika a modules/ui/utils/rqi.ts köré
   szerveződjön, ne szórd szét.

Megkötés: npm run typecheck && npm run lint && npm test zöld; commit csak kérésre.
Ha a színskálát vizuálisan ellenőrzöd, egy screenshot a térképről jó záró lépés.
```

---

## E4 — YOLO damage-modell frissítése + FastSAM-döntés

```
A repó: /Users/i/Dev/smooth-route
Olvasd el az AGENTS.md útválasztót. Ez backend/ML-YOLO feladat — nyisd meg a
docs/IMPROVEMENT_PLAN.md B3 és E4 pontját, és a backend training részét
(training_service.py, training/local_provider.py YOLO-ág, preprocessing.py).
Az RQI/DINO pipeline-t (ml/) NE módosítsd — az külön él.

Feladat: tanítsd újra a YOLO úthiba-detektort a friss annotációkból, és döntsd
el a FastSAM előfeldolgozó sorsát (B3).
1. Mérd fel, hány új annotált kép áll rendelkezésre (training_data.annotations).
2. Futtasd a meglévő YOLO-tanítási utat; hasonlítsd a mostani modellhez.
3. Döntés a FastSAM-ról: ha a nyers vagy geometriai ROI ugyanolyan jó, vezesd ki
   a FastSAM-ot (a preprocessing.py-t és a FastSAM-s.pt-t); ha kell, tartsd meg,
   de dokumentáld, miért.

Megkötés: az RQI-motor és a térképi RQI változatlan marad; tesztkapuk zöldek;
commit csak kérésre. A döntést írd le a MODEL_EXPERIMENTS.md-be.
```

---

## E1 — Címkézés a 3↔4 határon (ez emberi feladat, de az ágens előkészítheti)

E1 maga **kézi címkézés** (te pontozol képeket), de egy ágens kigyűjtheti a
leghasznosabb képeket ("active learning": ahol a modell a legbizonytalanabb).

```
A repó: /Users/i/Dev/smooth-route
Olvasd el az AGENTS.md útválasztót, majd CSAK az "RQI-modell / ml/" sort.

Feladat: gyűjtsd ki a ~150 legbizonytalanabb, 3↔4 határ közeli képet, hogy
kézzel újracímkézhessem őket (a hibák zöme itt van).
1. Az ml/cache/oof_table.csv (out-of-fold predikciók) alapján válaszd ki azokat
   a képeket, ahol a folytonos becslés a 3.0–4.0 sávba esik ÉS a P(rossz) a
   0.35–0.65 bizonytalan tartományban van.
2. Írd ki egy listába (kép elérési út + jelenlegi becslés + P(rossz)), a
   legbizonytalanabbtól rendezve, hogy a review-felületen végigmehessek rajtuk.
3. Ne módosítsd a modellt; ez csak előkészítés a címkézésemhez.

Megkötés: commit csak kérésre.
```

---

## Ellenőrző prompt (bármely fázis után)

```
A repó: /Users/i/Dev/smooth-route
Olvasd el az AGENTS.md útválasztót. Ne írj új funkciót.

Feladat: ellenőrizd a legutóbbi <<fázis/PR>> munkát.
1. Futtasd az összes tesztkaput (backend pytest; frontend typecheck/lint/test),
   és ha RQI-modell változott, az ml/evaluate_artifact.py kaput is.
2. Nézd át a diffet: megfelel-e az IMPROVEMENT_PLAN elfogadási kritériumainak,
   maradt-e halott kód vagy elavult doksi.
3. Összegezz: mi zöld, mi nem, mit javasolsz. Ne javíts, csak jelentsd — kivéve
   ha kifejezetten kérem.
```

---

## F0–F6 — Publikálási fázisok (auth, queue, kvóták, deploy)

```
A repó: /Users/i/Dev/smooth-route

Először olvasd el az AGENTS.md útválasztót. A feladatod a publikálási terv
egy fázisa: nyisd meg a docs/PUBLISH_PLAN.md-t, és CSAK a saját fázisod
(F<<N>>) szakaszát dolgozd fel + a rá vonatkozó közös szakaszokat
(adatmodell, kvóta/dedup-terv, hardening-checklist). A többi fázis részleteit
ne olvasd be.

Feladat: hajtsd végre az F<<N>> fázist a PUBLISH_PLAN.md checklistje szerint.

Megkötések:
- Python: mindig a .venv/bin/python; ne hozz létre új venv-et.
- A tesztkapuknak zöldnek kell lenniük a végén:
    cd backend && ../.venv/bin/python -m pytest -q
    cd frontend && npm run typecheck && npm run lint && npm test
- A fázis "Elfogadás" kritériumát bizonyítsd (teszt vagy kézi ellenőrzés
  leírása), és pipáld ki az elkészült checklist-elemeket a PUBLISH_PLAN.md-ben.
- Titkok (API-kulcs, Clerk secret) SOSEM kerülhetnek a repóba.
- A végén foglald össze a diffet és a tesztek eredményét. Commit/push CSAK
  explicit kérésre.
```

---

## F1 — User-modul (auth + szerepek) — ELŐREHOZVA, ez az első publikálási lépés

```
A repó: /Users/i/Dev/smooth-route

Először olvasd el az AGENTS.md útválasztót. A feladatod a publikálási terv F1
fázisa: a docs/PUBLISH_PLAN.md-ből CSAK az "F1 — Auth és szerepek" szakaszt,
az "Adatmodell-változások" és a "Jogosultsági szintek" szakaszt olvasd el.
A többi fázis (F2–F6) részleteit NE olvasd be.

Feladat: fejleszd ki a user-modult lokálisan (Clerk dev-instance-szal), a
PUBLISH_PLAN F1-checklistje szerint:

1. Előfeltétel-ellenőrzés: kell CLERK_SECRET_KEY a gyökér .env-be és
   VITE_CLERK_PUBLISHABLE_KEY a frontend env-jébe. Ha hiányoznak, építsd meg
   a kódot mockolt/tesztelhető JWT-verifikációval, és a session végén sorold
   fel pontosan, mit kell a Clerk-dashboardon kézzel létrehozni (app,
   email+jelszó és Google provider), hova kerülnek a kulcsok.
2. F0-ból előrehozva, mert séma-változás lesz: Alembic bevezetése baseline
   migrációval a jelenlegi sémáról; a users tábla már migrációként jöjjön.
3. Backend: JWT-verifikáló dependency (Clerk JWKS), users tábla
   (id, clerk_id unique, email, role: 'user'/'admin') JIT-provisioninggal;
   Strawberry permission-osztályok (IsAuthenticated, IsAdmin); a
   training/review/settings mutációk admin-only, a route-indítás user-only;
   a REST /api/v1/* végpontok ugyanezzel a dependency-vel védve.
   A térkép-OLVASÁS anonim marad (elfogadott termékdöntés).
4. Frontend: @clerk/clerk-react — SignIn/SignUp, user-menü; Apollo authLink
   a Clerk session-tokennel; admin-only menüpontok elrejtése user elől.
5. Tesztek: a permission-guardok unit-tesztje mockolt tokennel (401/403 utak);
   a meglévő tesztek ne törjenek.

Megkötések:
- Python: mindig a .venv/bin/python; ne hozz létre új venv-et.
- A tesztkapuknak zöldnek kell lenniük a végén:
    cd backend && ../.venv/bin/python -m pytest -q
    cd frontend && npm run typecheck && npm run lint && npm test
- Titkok (Clerk secret, API-kulcsok) SOSEM kerülhetnek a repóba — env-ből.
- Menet közben jegyezd fel, milyen VALÓS szükségletek derülnek ki (mi hiányzik
  a tervből, mi felesleges) — ez a session egyik célja; a végén ezt külön
  szakaszban foglald össze, és javasolj PUBLISH_PLAN-módosítást, ha indokolt.
- Pipáld ki az elkészült F1-checklist-elemeket a docs/PUBLISH_PLAN.md-ben.
- A végén foglald össze a diffet és a tesztek eredményét. Commit/push CSAK
  explicit kérésre.
```
