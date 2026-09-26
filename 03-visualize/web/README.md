# jevviz frontend

Vite + React + TypeScript app that renders the flat json-render spec emitted by the
`jevviz` Python backend. All ranking/selection logic lives server-side; this app only
renders the five component types (`Grid`, `Panel`, `Chart`, `Kpi`, `Table`) via a
json-render catalog and registry.

## Scripts

- `npx vitest run` — unit tests (jsdom)
- `npx tsc -b` — type-check (project uses TS project references; `tsc --noEmit` alone
  is a no-op here because the root `tsconfig.json` has `"files": []` and only
  `references`)
- `npm run dev` — Vite dev server, proxies `/run` and `/health` to `http://127.0.0.1:8000`

## Differences between the installed `@json-render/*` (0.21.0) and the docs-derived usage

The task brief's example code was written from documentation, not from the installed
package. Per the task's Ruling R1, the installed API was used as the source of truth.
Differences found:

1. **`Renderer` requires an `ActionProvider` ancestor even when the catalog declares no
   actions.** The brief's documented provider tree is
   `StateProvider > VisibilityProvider > Renderer`. In 0.21.0, `Renderer`'s internal
   element renderer unconditionally calls the `useActions()` hook, which throws
   `"useActions must be used within an ActionProvider"` if no `ActionProvider` is an
   ancestor — regardless of whether the catalog defines any actions. We render with:

   ```tsx
   <StateProvider initialState={{}}>
     <VisibilityProvider>
       <ActionProvider>
         <Renderer spec={spec} registry={registry} />
       </ActionProvider>
     </VisibilityProvider>
   </StateProvider>
   ```

   `ActionProvider` is exported from `@json-render/react` and defaults `handlers` to
   `{}`, so no extra wiring is needed for a catalog with `actions: {}`. This does not
   change the wire spec shape produced by the backend — it is purely a React provider
   requirement on the frontend.

2. **`@testing-library/jest-dom` (7.0.1) does not auto-augment Vitest's `expect`
   types.** The plain `import "@testing-library/jest-dom"` only declares matcher types
   under the Jest global namespace (see `types/jest.d.ts` in that package), so
   `expect(...).toBeInTheDocument()` fails to type-check under `tsc -b` even though it
   works at runtime. The package ships a dedicated `@testing-library/jest-dom/vitest`
   subpath (`types/vitest.d.ts`) that augments Vitest's `Assertion` /
   `AsymmetricMatchersContaining` interfaces instead. `registry.test.tsx` imports that
   subpath. (Not a json-render difference, but recorded here since it was required to
   get a clean `tsc -b`.)

All exports used (`defineCatalog` from `@json-render/core`; `defineRegistry`,
`Renderer`, `StateProvider`, `VisibilityProvider`, `ActionProvider`, `schema` from
`@json-render/react`) match the brief's expected names exactly — only the provider
tree needed the addition above. No `experimental_*` API was used.

`zod` `4.6.5` was installed; both `@json-render/core` and `@json-render/react` declare
a peer/dependency range of `^4.0.0` / `^4.3.6`, so no version pin was needed.

## Rows via context, not json-render state

`RowsContext` (`web/src/rows.ts`) carries the shared row array to `Chart`, `Kpi`, and
`Table` components directly via React context, not through json-render's `$state`
mechanism. This is a deliberate, plan-declared deviation from the design spec: it
keeps a up-to-5,000-row array out of the spec/diffing path entirely — rows are sent
once and every chart reads them by name (`data: {"name": "rows"}` in each Vega-Lite
spec), matching spec §8.
