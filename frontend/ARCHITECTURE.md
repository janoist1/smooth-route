# Frontend Framework Architektúra

Ez a dokumentum a Smooth Route frontend rendszerének technikai alapjait és tervezési filozófiáját írja le. Célja, hogy bevezesse az új fejlesztőket a "Framework First" gondolkodásmódba, amely megkülönbözteti ezt a projektet a hagyományos React alkalmazásoktól.

---

## 1. Tervezési Filozófia: Inversion of Control

Egy hagyományos kliens oldali alkalmazásban gyakran a UI komponensek vezérlik az üzleti logikát (pl. `useEffect`-ben indított adatlekérések). Ez azonban skálázódási problémákhoz, "Waterfall" betöltéshez és nehezen tesztelhető kódhoz vezet.

Ebben a projektben **megfordítottuk a vezérlést (Inversion of Control)**:

- **A Keretrendszer (The Engine)**: Felelős az alkalmazás életciklusáért, a navigáció koordinálásáért és az erőforrások menedzseléséért.
- **A Modulok (Feature Modules)**: Kizárólag a domén-specifikus szabályokat és a megjelenítést tartalmazzák, reagálva a Keretrendszer utasításaira.

---

## 2. Architektúrális Pillérek

### A. Universal Modular Architecture (UMA)

A kódbázis nem technikai rétegek (views, controllers), hanem **üzleti funkciók** szerint szerveződik. Minden modul egy önálló egység, szigorúan definiált határokkal.

```text
src/modules/training/
├── components/       # UI (Buta komponensek)
│   └── TrainingView.tsx
├── hooks.ts          # Controller (Public API a UI felé)
├── index.ts          # Gatekeeper (Public API a rendszer felé)
├── sagas.ts          # Side Effects (API hívás, mentés)
├── slice.ts          # State (Redux)
└── types.ts          # TypeScript interfészek
```

**Szabály**: Komponens sosem importálhat a `slice.ts`-ből vagy `sagas.ts`-ből. Kizárólag a `hooks.ts` és `index.ts` érhető el kívülről.

### B. Központi Saga Vezérlés (Orchestration)

#### 1. Blocking App Start (Initialization Guard)

Az alkalmazás indításakor a UI (`App.tsx`) jelez a rendszernek, hogy készen áll. Ez indítja el a blokkoló szinkronizációs folyamatot.

```typescript
// App.tsx

const AppContent: React.FC = () => {
  useAppStart() // 2. App start esemény
  const app = useApp()

  if (app.loading) {
    return <div style={{ color: 'white', padding: 20 }}>Loading...</div>
  }
  ...
}

// routerSaga.ts (The Guard)
function* routerSaga() {
  // 1. Várakozás a rendszer felállására (BLOCKING)
  yield call(waitForAppStart)

  // 3. Csak ezután indulhat a navigáció figyelése
  yield takeLatest(LOCATION_CHANGE, handleLocationChange)
}
```

#### 2. Navigation Driven Data Fetching

Az adatbetöltés nem komponens életciklushoz, hanem útvonalváltáshoz kötött.

```typescript
// routerSaga.ts
function* handleLocationChange(action) {
  const { pathname } = action.payload

  // Ha a training oldalra léptünk...
  if (matchPath(pathname, '/training/:id')) {
    const id = extractId(pathname)

    // ...utasítjuk a modult az inicializálásra.
    // A komponensnek nem kell tudnia róla, hogy ez most történik.
    yield put(trainingActions.fetchImage(id))
  }
}
```

### C. Type-Safe Tooling

A `saga-toolkit` segítségével összekötjük az Action-t a Saga Handlerrel, így a típusosság végig megmarad.

```typescript
// Definíció (slice.ts)
// Input: number (ID) -> Output: TrainingData
export const fetchImage = createSagaAction<number, TrainingData>('training/fetch')

// Használat (sagas.ts)
// A rendszer automatikusan tudja, hogy a payload 'number'
yield takeLatestAsync(fetchImage.type, function* (action) {
  const id = action.payload // number
  // ...
})
```

### D. Saga Pattern: Array of Effects

A redundáns csomagolás (`function* rootSaga() { yield all(...) }`) elkerülése érdekében a modulok sagái **nem generator függvényt**, hanem **effekt tömböt** (`ForkEffect[]`) exportálnak.

```typescript
// modules/myModule/sagas.ts
export default [
  takeLatest(actions.fetch.type, fetchWorker),
  takeLatest(actions.save.type, saveWorker),
]

// store.ts
function* rootSaga() {
  yield all([...mapSagas, ...trainingSagas])
}
```

Ez tisztább, deklaratívabb kódot eredményez és könnyebb összeilleszteni a modulokat a főágban.

---

## 3. Implementációs Útmutató (Workflow)

Új funkció fejlesztésekor kövesd szigorúan ezt a lépéssort:

### 1. Adatmodell (`slice.ts`)

Definiáld az állapotot és a szinkron módosítókat. Használd a `createSagaAction`-t aszinkron műveletekhez.

```typescript
const slice = createSlice({
  name: 'training',
  initialState,
  reducers: {}, // Csak szinkron műveletek
  extraReducers: builder => {
    // Reagálás az aszinkron folyamatokra
    builder.addCase(fetchImage.pending, state => {
      state.loading = true // Azonnali feedback
    })
    builder.addCase(fetchImage.fulfilled, (state, { payload }) => {
      state.data = payload
      state.loading = false
    })
  },
})
```

### 2. Üzleti Logika (`sagas.ts`)

Implementáld a mellékhatásokat. Itt történik az API kommunikáció és a komplex logika.

```typescript
function* fetchImageWorker(action) {
  try {
    // GraphQL hívás
    const data = yield call(api.getTrainingData, action.payload)
    // Siker -> Reducer frissítése
    yield put(fetchImage.fulfilled(data))
  } catch (e) {
    yield put(fetchImage.rejected(e))
  }
}
```

### 3. Controller (`hooks.ts`)

Csomagold be a logikát egy Hook-ba. Ez az EGYETLEN felület, amit a React komponens láthat.

```typescript
export const useTraining = () => {
  const dispatch = useDispatch()
  // Selectorok használata
  const data = useSelector(selectTrainingData)

  return {
    data,
    // A komponens nem tudja, hogy ez saga vagy reducer, csak "menteni" akar.
    save: id => dispatch(saveTraining(id)),
  }
}
```

### 4. View (`components/MyView.tsx`)

A komponens kizárólag a Hook-ból származó adatokat jeleníti meg. Nincs `useEffect` adatlekérésre!

```typescript
const TrainingView = () => {
  const { data, loading } = useTraining();

  if (loading) return <GlobalLoader />;

  return <div>{data.title}</div>;
};
```

---

## 4. Összegzés

Ez az architektúra nagyobb kezdeti fegyelmet igényel, de cserébe:

1.  **Kiszámítható**: Mindig tudod, hol keresd a logikát (Saga) és hol az állapotot (Slice).
2.  **Típusbiztos**: A `saga-toolkit` végigvezeti a típusokat a rendszeren.
3.  **Skálázható**: Az új modulok nem lassítják a régieket, mivel teljesen izoláltak.
