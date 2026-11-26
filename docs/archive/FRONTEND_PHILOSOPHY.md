# Frontend Architektúra és Filozófia

Ez a dokumentum a `smooth-route` frontendjének technikai döntéseit, tervezési mintáit és a fejlesztés során felmerült kihívásokra adott válaszokat összegzi. Célja, hogy átfogó képet adjon a rendszer lelkéről új fejlesztők és a jövőbeli karbantartás számára.

---

## 1. Architektúrális Alapelvek: Modularitás és Rétegződés

A projekt a **Feature-based** szervezést követi a `src/modules` mappában.

### A Filozófia

Nem technológia szerint csoportosítunk (pl. _all components here_, _all reducers there_), hanem üzleti funkciók szerint (pl. `training`, `ui`, `auth`, `map`). Ez skálázhatóbbá teszi a kódot: ha a "Training" funkciót kell javítani, minden (state, saga, komponens, típus) egy helyen van.

### A Rétegek

Kiemelt figyelmet fordítunk a **Presentational vs. Container** (Buta vs. Okos) komponensek szétválasztására.

- **"Buta" Komponensek (UI Library):** Pl. `src/modules/training/components/TrainingList`, `AnalysisPanel`.
  - **NEM** tudnak a Redux-ról.
  - Csak `props`-okon keresztül kommunikálnak.
  - Könnyen tesztelhetők és újrahasznosíthatók.
- **"Okos" Komponensek (Pages/Connectors):** Pl. `src/components/pages/TrainingDashboardPage.tsx`.
  - Itt történik a Redux `useTraining` hook bekötése.
  - Itt kezeljük a navigációt (`useNavigate`).
  - Ez a "ragasztó" réteg az adat és a megjelenítés között.

> **Fejlesztői Tipp:** Ha új funkciót írsz, kérdezd meg magadtól: "Működne ez a komponens Storybook-ban, Redux nélkül?" Ha nem, próbáld meg szétválasztani a logikát a megjelenítéstől!

---

## 2. Adatkezelés: Single Source of Truth

### Redux vs. Apollo Client

A rendszerben **kettős adatréteg** van, de szigorú hierarchiával:

1.  **Redux (Toolkit):** Ez az **egyetlen igazság forrása** (Single Source of Truth) a UI számára. Minden adat, állapot, ami a képernyőn megjelenik, a Redux store-ból jön.
2.  **Apollo Client:** Kizárólag **transport layer**-ként (adatátvivőként) funkcionál.
    - Beállítás: `fetchPolicy: 'no-cache'`.
    - Miért? Hogy elkerüljük az "osztott állapot" problémáját, ahol az Apollo Cache és a Redux Store eltérő adatokat mutat. A szervertől kapott adatot a Saga azonnal betölti a Reduxba, és onnan olvassuk.

### DevTools Teljesítmény

A nagy adathalmazok (pl. térkép pontok) miatt a Redux DevTools hajlamos belassulni. Ezért a `store.ts`-ben **Sanitizer**-eket használunk, amik levágják a túl nagy payload-okat a logokban. Ez nem érinti a működést, csak a fejlesztői eszközök sebességét javítja.

---

## 3. Aszinkron Folyamatok: Redux Saga Minták

Mivel a projekt komplex, hosszan futó folyamatokat (pl. AI tanítás, elemzés) kezel, a `redux-thunk` nem volt elég. A **Redux Saga** generátorai adják a vezérlést.

### A "Polling" Minta és Race Condition Kezelés

A legkritikusabb rész a backend folyamatok (Job-ok) követése. Itt több csapdát is elkerültünk:

#### 1. Saga Cancellation (A folyamat szintjén)

Ha a felhasználó navigál vagy újat kattint, a régi, futó pollert "le kell lőni".
Használjuk a `cancelled()` effektet. Ha egy pollert megszakítunk, a `finally` blokkban ezt detektáljuk, és **NEM** futtatjuk le a befejező logikát (pl. `jobCompleted` action dispatch-elése).

```typescript
// Minta (sagas.ts):
try {
   while (true) { ...polling... }
} finally {
   if (yield cancelled()) {
      // Megszakítva: Csak takarítunk (channel close), nem dispatch-elünk eredményt!
   } else {
      // Sikeres futás: Eredmény feldolgozása
      yield call(checkFinalJobStatus, jobId)
   }
}
```

#### 2. Attached Fork Csapdája (Az életciklus szintjén)

A `saga-toolkit` `takeLatestAsync` használatakor, ha `fork`-olunk egy pollert, az "Attached" marad. A szülő action (`fulfilled`) csak a poller leállása _után_ fut le.

- **Hiba volt:** A `fulfilled` reducerben visszaállítottuk a státuszt `running`-ra.
- **Következmény:** A poller beállította a `completed`-et, majd ezredmásodpercekkel később a szülő `fulfilled` felülírta `running`-ra.
- **Javítás:** A `fulfilled` ágban már nem bántjuk a státuszt.

#### 3. State Guard (Az adat szintjén)

Bevezettünk egy "Defenzív Reducer" logikát. Egy Job állapota nem mehet visszafelé koncepcionálisan:

- `Completed` -> `Running`: **TILOS** (kivéve ha explicit új ID jön létre).
  Ez megvédi a UI-t akkor is, ha a backend (vagy egy beragadt régi poller) "running" státuszt küldene egy már kész jobra.

### Signal Actions vs. Async Actions

- **Async Action (`createSagaAction`):** Akkor használjuk, ha kell a `pending`/`fulfilled` állapot a UI-n (pl. `fetchList`).
- **Signal Action (`createAction`):** Olyan műveleteknél, mint a `reconnectJob`, ahol nem várunk választ, csak egy folyamatot indítunk el. Ezeket sima `takeLatest` figyeli. Ez csökkenti a boilerplate kódot.

---

## 4. Routing és Navigáció: URL-Driven State

A rendszer a "Single Source of Truth" elvét a navigációra is kiterjeszti: **Az URL a vezérlő.**

- **Router Saga (`sagas/router.ts`):** Nem a komponensek `useEffect`-jében hívunk API-t.
- Helyette a Router Saga figyeli az URL változást. Ha a felhasználó a `/training/dashboard?mode=pending` oldalra lép, a Saga automatikusan dispatch-eli a `fetchList({ mode: 'pending' })` action-t.
- **Előnye:**
  - Tökéletes Deep Linking támogatás.
  - Leválasztja az adatbetöltést a komponens életciklusáról (nincs "waterfall" fetching).
  - Központosított logika.

---

## 5. UX Filozófia: "Fresh Start"

Hosszú kísérletezés után alakult ki a Reconnection (oldal újratöltés) logikája.

- **Probléma:** Ha a user frissít, és a legutóbbi job már "Completed", zavaró, ha a UI újra mutatja a "Kész" üzenetet, mintha most történt volna valami.
- **Döntés:** Ha a job már kész, az oldal újratöltésekor **alaphelyzetbe (`idle`)** hozzuk a rendszert. Csak akkor mutatunk státuszt, ha az _valóban fut_.
- **Perzisztencia:** Jelenleg nem mentjük az elemzési eredményeket (`exports`) LocalStorage-ba. Ha a usernek szüksége van az eredményre, le kell töltenie a folyamat végén.

---

Ez a dokumentum szolgáljon iránytűként. A kód minősége nem csak a működésben, hanem a struktúra tisztaságában és a döntések tudatosságában rejlik.
