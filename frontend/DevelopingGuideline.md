# Universal Modular Architecture (UMA): The Unified Blueprint

Ez a dokumentum a **Universal Modular Architecture (UMA)** hivatalos kézikönyve. Ezt a modern, magas szintű szoftverarchitektúrát úgy terveztük, hogy skálázható alapot nyújtson a hosszú távú fejlesztéshez, miközben maximalizálja az AI-asszisztált kódolás hatékonyságát.

Az architektúra központi gondolata a **“Master-Submodule” hierarchia**, amely az alkalmazást funkcionális egységekre tagolja, miközben éles határvonalat húz az üzleti logika hordozói (Sub-Modules) és az alkalmazás összeállítója (Master Module) között.

Ez nem csak szabályok gyűjteménye, hanem egy gondolkodásmód (mindset). A célunk az, hogy a kód még évek múlva is átlátható és módosítható maradjon.

---

## 1. Főbb Előnyök (Miért jó ez neked?)

-   **Izolált Kontextus (The Black Box Principle)**:
    Minden modul (`src/modules/*`) egy önálló kis univerzum. Saját állapota, logikája és API-ja van. Ez azt jelenti, hogy ha a `User` modulban dolgozol, nem kell fejben tartanod a `Content` modul belső működését. Ez csökkenti a kognitív terhelést.

-   **Magas DX (Developer Experience)**:
    A konzisztencia király. Bárhol jársz a kódbázisban, mindig ugyanazt a szerkezetet találod (`slice`, `sagas`, `hooks`). Nincs "meglepetés" kód, nem kell kitalálni, hova tette az előző fejlesztő az üzleti logikát.

-   **AI-Native Design**:
    Az LLM-ek (mint Claude vagy GPT) szeretik a tiszta határokat. Mivel a moduljaink szeparáltak és szabványosak, az AI sokkal pontosabban tud kódot generálni hozzájuk, mert nem kell a teljes projektet "látnia", elég neki az adott modul kontextusa.

-   **Zero-Prop-Drilling**:
    A Prop Drilling (amikor 5 szinten keresztül adogatunk le adatot) a React fejlesztés egyik legnagyobb fájdalma. A **Power Hook** mintával (`useFeature`) a komponensek közvetlenül a forrásból kapják az adatot, ott, ahol szükségük van rá.

-   **Dumb Components (A UI Tehermentesítése)**:
    A komponenseknek egyetlen dolga van: a megjelenítés. Nem tartalmaznak üzleti logikát, validációt vagy adattranszformációt. Minden "nehéz" műveletet a modulok (Sagas, Selectors) végeznek el. Ezáltal a UI kódja radikálisan egyszerűsödik és könnyebben cserélhető.

-   **Design for Testability**:
    Mivel az üzleti logika levált a UI-ról (Sagas, Reducers), a rendszer kritikus részei böngésző és React renderelés nélkül, gyors és stabil unit tesztekkel ellenőrizhetők. Nem kell bonyolult E2E teszteket írni minden apróságra.

---

## 2. Alapelvek & Filozófia

### 2.1. Organic Growth (Szerves Növekedés)
Sokan félnek az "architektúra" szótól, mert bonyolult boilerplate kódra asszociálnak. Az UMA kerüli ezt.
-   **Kezdj kicsiben**: Egy új modul állhat egyetlen `index.ts` fájlból is.
-   **Növekedj igény szerint**: Csak akkor hozd létre a `components`, `hooks` vagy `utils` mappákat, ha a fájl mérete vagy a feladat komplexitása ezt indokolja. Ne építs fel előre üres "templomokat".

### 2.2. Orchestration vs. Implementation
Ez a legfontosabb szétválasztás.
-   **Implementation (Hogyan?)**: A `src/modules/` mappa dolga. Itt van a *tudás* (hogyan mentünk el egy usert, hogyan számoljuk ki az árfolyamot).
-   **Orchestration (Mikor és Hol?)**: A `src/components/` és `src/sagas.ts` dolga. Itt dől el, hogy *mikor* hívjuk meg a logikát (pl. kattintásra, navigációra) és *hol* jelenítjük meg az eredményt.

---

## 3. Az Architektúra Szintjei (The Hierarchy)

A rendszer két, egymástól élesen elválasztott szintre ("emeletre") tagolódik. A szintek közötti kommunikáció szigorúan szabályozott.

### 3.1. Level 0: The Assembly Layer (`src/`)
Ez a gyökér szint, az "Összeszerelő Üzem". Itt nincsenek bonyolult üzleti szabályok. A feladata, hogy a `modules/`-ból érkező építőkockákat összeillessze egy működő alkalmazássá.
-   **Logic Assembly (`src/store/`)**: Itt "dugjuk össze" a modulokat. A Redux Store itt regisztrálja a modulok reducer-eit és sagáit.
-   **View Assembly (`src/components/`, `src/app/`)**: Itt állnak össze az oldalak. A `Router` itt dönti el, melyik képernyő látszik.
-   **Master Orchestrator (`src/sagas.ts`)**: Itt futnak a globális, modulokon átívelő folyamatok (pl. "App Indítása", ami érinti az Auth, Config és User modulokat is).

### 3.2. Level 1: The Module Layer (`src/modules/`)
Ez az alkalmazás "agya". Itt lakik az üzleti érték.
**Aranyszabály**: Level 1 soha, semmilyen körülmények között nem importálhat Level 0-ból. A függőség iránya mindig fentről lefelé mutat (`Level 0 -> Level 1`).

### 3.3. Module Taxonomy (Modul-taxonómia)
Nem kezelünk minden kódot egyformán. Három kategóriát különböztetünk meg a felelősségük alapján:

1.  **Domain Modules** (pl. `User`, `Content`): Az üzleti entitások lakhelye. Itt vannak az állapotok, a szabályok és az API hívások.
2.  **Service Modules** (pl. `API`, `Logger`, `Storage`): Technikai szolgáltatások. Ezek "buta" eszközök, amiket a Domain modulok használnak a feladataik elvégzésére.
3.  **Foundation Modules** (pl. `UI-Kit`, `Formik`): Közös UI elemek és segédkönyvtárak. Teljesen függetlenek az üzlettől (pl. egy Gomb komponens nem tudja, mi az a "User").

### 3.4. Reference Directory Structure (Minta és Magyarázat)
A fájlrendszerünk szándékosan tükrözi a logikai felépítést (**State Mirroring**).

```text
src/
├── components/           # [Level 0] View Assembly
│   └── App.tsx           # A főkomponens, ami összerakja a layoutot
├── routes.ts             # [Level 0] Routing definíciók (nem szerves UMA rész, de ajánlott minta)
├── store/                # [Level 0] Logic Assembly
│   ├── rootReducer.ts    # "The Fuse Box" - Itt egyesítjük a slice-okat
│   └── createStore.ts    # "The Engine" - Itt indítjuk a Redux-Saga middleware-t
├── sagas.ts              # [Level 0] Master Orchestrator
│                         # (Rendszerszintű folyamatok helye, pl. init)
├── modules/              # [Level 1] The Brain (Sub-Modules)
│   ├── user/             # [Domain Module] -> Ez a mappa felel a state.user-ért
│   │   ├── slice.ts      # Redux State & Actions
│   │   ├── sagas.ts      # Aszinkron folyamatok (API hívások)
│   │   └── index.ts      # A modul publikus kapuja (Gatekeeper)
│   ├── api/              # [Service Module]
│   │   ├── client.ts     # Axios/Amplify beállítások
│   │   └── hooks.ts      # React Query vagy egyedi hook-ok
│   └── ui/               # [Foundation Module]
│       └── Button.tsx    # Újrafelhasználható UI komponens
```

**Miért jó ez a struktúra?**
-   **State Mirroring**: Ha tudod, hogyan néz ki az adat a Redux DevTools-ban (`state.user`), akkor pontosan tudod, melyik mappában keresd a kódot (`modules/user`).
-   **Predictable Assembly**: A `src/store` igazából csak egy konfigurációs mappa. Ha új modult adsz hozzá, itt csak regisztrálnod kell, a valódi munka a modulon belül zajlik.
-   **Kereshetőség (Colocation)**: Minden, ami egy funkcióhoz tartozik (state, logika, UI), egy helyen van. Nem kell a projekt különböző pontjain (actions, reducers, sagas mappákban) vadásznod a fájlokat.

---

## 4. Sub-Module Felépítése

Hogyan néz ki belülről egy **Domain Module**? A fájlok szerepei szabványosak:

```text
[module]/
├── components/   # A modulhoz tartozó speciális UI elemek (nem globálisak)
├── slice.ts      # A "Mit": Állapotdefiníció és szinkron akciók
├── sagas.ts      # A "Hogyan": Mellékhatások, API hívások, komplex logika
├── selectors.ts  # State olvasás: Memoizált szelektorok a gyors eléréshez
├── hooks.ts      # Az interfész: Ezen keresztül beszélget a React a Modullal
└── index.ts      # A kapu: Csak azt engedi ki, amit a külvilág láthat
```

### 4.1. The Gatekeeper Pattern (`index.ts`)
Ez a fájl a modul tűzfala. Ami nincs itt exportálva, az **privát**. Ez megakadályozza, hogy más fejlesztők véletlenül belső, implementációs részletekre építsenek, amik később változhatnak.

```typescript
// index.ts
// Csak a publikus API-t exportáljuk
export * as actions from './slice';
export * as selectors from './selectors';
export { default as sagas } from './sagas'; // A root sagának kell
export { default as slice } from './slice'; // A root reducernek kell
export * from './hooks'; // A komponenseknek ez a fő belépési pont
```

---

## 5. Megoldások Gyakori Kihívásokra (Common Patterns)

Az alábbiakban bemutatjuk, hogyan kezeljük a fejlesztés során felmerülő tipikus problémákat (aszinkronitás, adatbetöltés) ebben a konkrét UMA implementációban. Ezek nem részei a szigorú architektúra definíciónak, de bevált gyakorlatok a projektben.

### 5.1. Kihívás: Aszinkron Folyamatok Kezelése -> Saga-Toolkit
A `saga-toolkit` használata azért javasolt, mert leveszi a válladról a terhet: automatikusan kezeli az aszinkron akciók állapotait (`pending`, `fulfilled`, `rejected`), így nem kell kézzel írnod a try-catch blokkokat mindenhol.

#### 5.1.1. Cross-Module Orchestration (`putAsync`)
Gyakori probléma: "El kell indítanom egy folyamatot, de meg kell várnom, amíg egy *másik* modul befejez valamit." Erre való a `putAsync`.

```typescript
function* initAppSaga() {
  // Megvárjuk, amíg az Auth modul befejezi a session ellenőrzést
  // Ez egy Promise-t ad vissza, amit a yield megvár/felold
  yield putAsync(authActions.checkSession()); 
  
  // Csak akkor fut le, ha a fenti hívás sikeres volt
  yield put(dataActions.loadInitialData());
}
```

### 5.2. Complex Data Handling Patterns

#### 5.2.1. Intelligens Lapozás (Pagination Loop)
Ahelyett, hogy a komponensbe raknánk a "következő oldal" logikát, a saga elintézi egyben. Ez tehermentesíti a UI-t.

```typescript
function* fetchItems() {
  const { queryVariables } = yield select(selectors.selectRoot);
  let items = [];
  let token = queryVariables.nextToken;

  // Addig kérdezgetjük az API-t, amíg van "nextToken" ÉS
  // el nem értük a kívánt mennyiséget.
  while (items.length < targetLimit) {
    const result = yield call(API.get, { ...queryVariables, nextToken: token });
    items = [...items, ...result.items];
    token = result.nextToken;
    if (!token) break; // Nincs több adat
  }
  return { items, nextToken: token };
}
```

#### 5.2.2. Kötegelt Feldolgozás (Batch Processing)
Ha 1000 elemet kell menteni, ne fagyaszd le a böngészőt. Dolgozd fel őket kisebb csomagokban (chunk), és adj visszajelzést (progress) a felhasználónak.

```typescript
function* processBatch({ meta }: SagaActionFromCreator<typeof actions.processAll>) {
  const { data, onProgress } = meta.arg;
  const size = 10; // 10-esével dolgozzuk fel
  
  for (let i = 0; i < data.length; i += size) {
    // Elküldjük a 10 elemet
    yield call(api.post, data.slice(i, i + size));
    
    // Frissítjük a UI progress bar-ját
    onProgress(i + size); 
  }
}
```

### 5.3. Derived State (Calculation Over Storage)
Kerüld a redundáns állapotok tárolását (pl. `isFullNameVisible`). Helyette számold ki őket a meglévő adatokból a selectorokban vagy a hookokban.

**Példa: Loading State**
Ne tárolj manuálisan `isLoading` boolean változókat minden művelethez. Helyette vezess be egy rendszerszintű megoldást (pl. aktív kérések számlálása vagy request ID alapú lookup), és ebből származtasd, hogy éppen tölt-e az adott funkció. Ez megakadályozza, hogy a UI "beragadjon" loading állapotba, ha egy hiba miatt nem jön válasz.

---

## 6. The Power Hook: Typing via Aggregation

A modulok publikus interfésze a React felé egyetlen, "okos" hook. Ez a hook összesíti (aggregálja) a modul tudását.

**Miért jó ez?**
Ahelyett, hogy a komponensben külön importálnád a Selectort, a Dispatch-et és az Action-öket, egyetlen sorban megkapsz mindent.

```typescript
type DynamicState = {
  loading: boolean
}
// A hook típusa egyesíti a:
// 1. Dinamikus (számított) állapotot
// 2. A Redux Store állapotát
// 3. Az elérhető akciókat
export const useFeature = (): DynamicState & actions.State & typeof actions => {
  const root = useSelector(selectors.selectRoot);
  const dispatch = useDispatch();

  return {
    ...root, // A modul state-je
    ...bindActionCreators(actions, dispatch), // Az akciók (már bekötve a dispatch-be)
    loading: root.runningTasks > 0, // A származtatott loading állapot
  };
};

// Használat a komponensben:
// const { users, loading, fetchUsers } = useUser();
```

---

## 7. Resilience & Standards (Stabilitás)

### 7.1. Global Notification Pattern
A felhasználó nem látja a `console.log`-ot. Ha hiba van, a rendszernek értesítenie kell őt. A sagákban a hibákat elkapjuk (`catch`), és egy központi üzenetküldő akcióval (`appActions.notify`) jelezzük a UI felé.

### 7.2. Navigation-Driven Data Fetching
Ez egy ajánlott minta a "Tiszta Komponensek" érdekében.
-   **Hagyományos**: A Komponens `useEffect`-ben kér le adatot (`mount` -> `fetch`).
-   **Navigation-Driven**: A Router váltás (`LOCATION_CHANGE`) indítja a `fetch`-et.
-   **Előny**: Mire a Komponens megjelenik, az adatlekérés már elindult (vagy be is fejeződött). Nincs "villogás" (layout shift), és a komponensnek nem kell tudnia az adatforrásról.

### 7.3. Testing Strategy
-   **Logic (Sagas)**: A `redux-saga-test-plan` könyvtárral teszteljük az *orkesztrációt* (pl. "ha hiba van, küld-e notify-t?").
-   **Integration (Hooks)**: A Power Hook-okat teszteljük, mert azok fedik le a modul publikus API-ját. Ha a hook működik, a mögötte lévő slice/selector is működik.
-   **Type Safety**: Kötelező a TypeScript szigorú használata. A `@ts-ignore` használata tilos ("Zero Tolerance"), mert aláássa a rendszer stabilitását.

---

## 8. The Golden Rules (Az Aranyszabályok)

Ezeket a szabályokat be kell tartani a rendszer integritásának megőrzése érdekében.

1.  **Bottom-Up Dependency**: Level 1 modul (User) soha nem importálhat Level 0-ból (App). Ez megakadályozza a "körbeérő" függőségeket, amik megölik a build folyamatot.
2.  **Explicit Public API**: Csak az `index.ts`-en keresztül kommunikálj más modulokkal. Ez a "szerződés" a modulok között.
3.  **Data Sovereignty**: Csak a `User` modul módosíthatja a `User` state-et. Mindenki más csak *kérheti* a módosítást (Action dispatch), de nem nyúlhat bele közvetlenül.
4.  **Smart Sagas, Dumb Components**: A saga dönti el, *mikor* és *hogyan* töltünk adatot. A komponens csak egy passzív megjelenítő (View), ami a pillanatnyi állapotot tükrözi.

---

## 9. AI Blueprint Prompt Template

Ezt a promptot másolhatod be az AI asszisztensnek (ChatGPT, Claude), hogy azonnal megértse a projekt kontextusát:

> "Act as a Senior Architect active in the **Universal Modular Architecture (UMA)**.
> 1.  **Context**: We use a strict Master-Submodule hierarchy (`src/` vs `src/modules`).
> 2.  **Classification**: Identify if the task involves **Domain**, **Service**, or **Foundation** logic.
> 3.  **Pattern**: Use **Saga-Toolkit** (`takeLatestAsync`, `putAsync`) and **Power Hooks**.
> 4.  **Technique**: Use **Navigation-Driven Fetching** and **RunningTasks** for state.
> 5.  **Output**: Generate code strictly respecting the Gatekeeper pattern (`index.ts` exports)."

---

## 10. Kihívások és Hátrányok (System Trade-offs)

Légy tisztában azzal, hogy mit áldozol fel az UMA-ért cserébe.

### 10.1. Architectural Rigor vs. Ad-hoc Speed
Az UMA fegyelmet követel.
-   **A Kihívás**: Nem tudsz csak úgy "gyorsan összeütni" egy funkciót. Létre kell hoznod a modult, a slice-ot, a sagát.
-   **A Trade-off**: A fejlesztés eleinte lassabbnak érződhet (a mentális teher miatt), de cserébe elkerülöd a "spaghetti code" kialakulását. A projekt 2 év múlva is ugyanolyan karbantartható lesz, mint az első napon.

### 10.2. Redux-Saga Tanulási Görbe
-   **A Kihívás**: A Generátorfüggvények (`function*`) és az Effect-ek (`call`, `put`) koncepciója nehezebb, mint az egyszerű `async/await`.
-   **A Trade-off**: Magasabb a belépési küszöb új fejlesztőknek. Cserébe viszont kapsz egy olyan eszköztárat (Race condition kezelés, Cancellation, Throttle), amivel triviális megoldani a legbonyolultabb aszinkron problémákat is.

### 10.3. Router Dependency in Logic
-   **A Kihívás**: A "Navigation-Driven" minta miatt a sagák tudnak az URL-ekről.
-   **A Trade-off**: Ez egy rejtett függőség (Implicit Dependency). Cserébe viszont a UI komponenseid teljesen tiszták maradnak, és újrahasznosíthatók bárhol, nem függnek az adatbetöltéstől.

---

## 11. Architectural Landscape (Piaci Körkép és Alternatívák)

Hol helyezkedik el az UMA a modern frontend architektúrák térképén? Miért ezt választottuk más népszerű megoldások helyett?

### 11.1. UMA vs. Feature-Sliced Design (FSD)
Az **FSD** egy rendkívül népszerű, de szigorú orosz módszertan, amely 6-7 rétegre osztja az alkalmazást (`app` -> `pages` -> `widgets` -> `features` -> `entities` -> `shared`).

-   **Miért nem FSD?**: Az FSD hierarchiája sok projekt számára túl bonyolult ("Analysis Paralysis"). Az UMA szándékosan "laposabb": csak két szintet különböztet meg (Level 0 és Level 1).
-   **A Döntés**: Az UMA a "Sweet Spot" a kaotikus struktúra és a túlkomplikált FSD között. Megtartja a modularitást, de kevesebb boilerplate kóddal.

### 11.2. UMA vs. Clean Architecture (Frontend)
A **Clean Architecture** (Robert C. Martin) szerint a keretrendszerek (React) és az adatbázisok (Redux Store) csak "technikai részletek", amiket el kell rejteni az üzleti logika elől.

-   **Miért nem Clean Arch?**: A React világban a State a rendszer gerince. Elrejteni a Redux-ot (pl. Repository pattern mögé) felesleges absztrakció, ami lassítja a fejlesztést.
-   **A Döntés**: Az UMA **"State Mirroring"**-et használ. Büszkén felvállaljuk, hogy a Redux State a Single Source of Truth, és ehhez igazítjuk a fájlrendszert is. Ez pragmatikusabb.

### 11.3. UMA vs. Modular Monolith (Nx / Turborepo)
A **Modular Monolith** megközelítésben a modulok fizikailag is külön csomagok (`libs/auth`, `libs/cart`), saját `package.json`-nal és build folyamattal.

-   **Miért nem Nx?**: Egyelőre nincs szükségünk arra, hogy a modulokat külön-külön publikáljuk vagy deployoljuk.
-   **A Döntés**: Az UMA a Modular Monolith "előszobája". Logikailag már szétválasztottuk a modulokat, de fizikailag még egy repóban, egy `src` mappában élnek. Ha a projekt hatalmasra nő, az UMA-ból a legkönnyebb átállni Nx-re.
