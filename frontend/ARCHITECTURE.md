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

## GraphQL types

Types are generated (`modules/graphql/generated/`): with the backend running,
`npm run codegen` (the `postcodegen` step runs `patch-apollo.sh`). Never hand-edit
generated files.

## Gates

`npm run typecheck && npm run lint && npm test && npm run build` — full gate list in
[AGENTS.md](../AGENTS.md). Unit-test saga logic; test a module's public surface
through its hook.
