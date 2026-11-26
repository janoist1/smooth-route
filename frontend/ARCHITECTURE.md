# Frontend architecture

Everything needed for work in `frontend/`; for the backend API see
[docs/API_SURFACE.md](../docs/API_SURFACE.md). Stack: React 19, Vite 8, Redux
Toolkit + redux-saga (`saga-toolkit`), Apollo Client 4 (transport only),
react-leaflet, Clerk, Vitest 4. Node 22+. UI text is Hungarian; code and comments
are English.

## Layout: two levels

```text
src/
├── components/        # Level 0 — view assembly: App, Routes, pages/
├── sagas/             # Level 0 — cross-module flows (app start, router)
├── store.ts, routes.ts
└── modules/<name>/    # Level 1 — feature modules: map, training, settings, auth, api, app, graphql, routing, ui
    ├── slice.ts       # state + actions
    ├── sagas.ts       # side effects (API calls); exports an ARRAY of effects, not a generator
    ├── selectors.ts
    ├── hooks.ts       # the module's public face to React ("power hook": useMap, useTraining, …)
    ├── components/    # the module's dumb UI components
    └── index.ts       # gatekeeper: only what is exported here is public
```

A new module can start as a single `index.ts`; add folders only when needed.

## Rules (mandatory)

1. **Dependency direction:** Level 1 (`modules/*`) never imports from Level 0.
2. **Public API only:** modules and components reach a module only through its
   `index.ts` / `hooks.ts`. Components never import `slice`, `sagas` or
   `selectors` — enforced by the ESLint `no-restricted-imports` rule.
3. **Data sovereignty:** a module's state is changed only by its own reducer;
   everyone else dispatches actions.
4. **Smart sagas, dumb components:** components do not fetch in `useEffect`; they
   render what the hook returns.
5. **Type safety:** no `@ts-ignore`.

## Established patterns

- **Navigation-driven fetching.** `sagas/router.ts` waits for app start
  (`waitForAppStart`), then on `LOCATION_CHANGE` dispatches the per-route load
  action (e.g. `/training/:id/review` → `trainingActions.fetchImage`). This gives
  deep links for free and avoids component fetch waterfalls.
- **Redux is the single source of truth; Apollo is transport.** The client runs
  with `fetchPolicy: 'no-cache'` (`modules/graphql/client.ts`); sagas put responses
  straight into the store and the UI reads from there.
- **Async vs. signal actions.** When the UI needs `pending/fulfilled/rejected`:
  `createSagaAction<Result, Arg>` (note the generic order: *output, input*) +
  `takeLatestAsync`. Fire-and-forget (e.g. `reconnectJob`): plain `createAction` +
  `takeLatest`.
- **Job polling (long background jobs).** (1) On cancel, the `finally` block checks
  `yield cancelled()` → clean up only, never dispatch a result. (2) A poller forked
  under `takeLatestAsync` is *attached*: the parent's `fulfilled` runs after the
  poller, so it must not rewrite the job status. (3) The reducer refuses
  `completed → running` (only a new job id may restart). (4) After a page reload a
  finished job is not shown again — only jobs that are actually running.
- **Derived state:** compute derivable values (e.g. `loading`) in selectors/hooks;
  don't store them.
- **DevTools:** the action/state sanitizers in `store.ts` truncate big point
  payloads; they only speed up DevTools.
- **RQI display logic** lives in one place: `modules/ui/utils/rqi.ts`.

## Map layers and road segments

What the map draws depends on the zoom (single rule: `layersForZoom` in
`modules/map/segments/style.ts`, used by both the router saga and `MapView`):

| Zoom | Layer | Source |
|---|---|---|
| < 13 | quality grid (average RQI per cell) | `roadQualityGrid` |
| 13–15 | road segments | `roadSegments(bbox, zoom)` |
| ≥ 16 | road segments + clickable frame dots | `roadSegments` + `points` |

Below zoom 16 the frame dots only appear around a selected segment. If the
backend does not know `roadSegments` (older deploy), the first failed request
flips `roads.supported` and the map keeps the legacy split (grid < 14, dots ≥ 14).

`modules/map/segments/` is a sub-module of `modules/map` with the usual layout
(own slice under the store key `roads`, sagas, selectors, `hooks.ts`):

- `style.ts`, `labels.ts`, `routeSummary.ts`, `geometry.ts` — pure rules
  (drawing, Hungarian wording, route maths); unit-tested, no React/Leaflet.
- `api.ts` — the GraphQL documents. Hand-typed `TypedDocumentNode`s until
  `npm run codegen` has seen the new schema; then drop the manual types.
- `sagas.ts` — `fetchSegments` is debounced and cancelled (`takeLatestAsync` +
  `delay`); `fetchRouteQuality` runs when `planRoute` succeeds.
- `mock.ts` — deterministic stand-in for the two queries. Enable with
  `VITE_MOCK_SEGMENTS=1`, or in the dev server with `?mockSegments=1`
  (`&mockCoverage=0` shows the "no data" route summary).

Components: `SegmentLayer` (imperative Leaflet layer on the shared canvas),
`SegmentDetailCard`, `RouteQualityCard` (inside `RoutePlanner`), `MapLegend`.
Layout that changes on a phone lives in `components/roadCards.css` (breakpoint
600 px, mirrored by `modules/map/screen.ts`).

## GraphQL types

Types are generated (`modules/graphql/generated/`): with the backend running,
`npm run codegen` (the `postcodegen` step runs `patch-apollo.sh`). Never hand-edit
generated files.

## Gates

`npm run typecheck && npm run lint && npm test && npm run build` — full gate list in
[AGENTS.md](../AGENTS.md). Unit-test saga logic; test a module's public surface
through its hook.

## What loads first (bundle budget)

Anonymous phone visitors on slow links download only the map. Keep it that way:

- **Pages:** only `HomePage` is in the initial bundle; every other route is
  `React.lazy` in `components/Routes.tsx` (each its own chunk, Hungarian
  "Betöltés…" fallback inside `RequireAdmin`).
- **Barrels:** code that runs at startup (`store.ts`, `sagas/router.ts`, map
  components) imports reducers, sagas, selectors and hooks **by file**
  (`modules/training/slice`, `modules/settings/hooks`, …), never through a module
  barrel that also exports page components — that would pull the page back in.
- **Clerk** lives only in `modules/auth/ClerkIsland.tsx`, a lazy chunk mounted
  *beside* the app (not around it) that portals the sign-in / user button into the
  nav slot (`UserMenu`). Nothing else may import `@clerk/*`. Until the island knows
  the sign-in state, `useViewer().loading` is true; requests from a visitor with a
  Clerk session cookie wait (≤ 10 s) for the token.
- **Vendors:** React, Leaflet and Apollo/GraphQL are separate long-cacheable chunks
  (`codeSplitting.groups` in `vite.config.ts`). Icons: named `lucide-react` imports
  are tree-shaken (only used icons ship).

Measured 2026-11-26 (map route, production build): 951 kB raw / 287 kB gzip in one
file before → 780 kB / 245 kB after; Clerk (90 kB / 25 kB) and the admin pages
(~85 kB / ~26 kB) load only when needed.
