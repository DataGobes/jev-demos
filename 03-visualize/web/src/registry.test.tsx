import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { ActionProvider, Renderer, StateProvider, VisibilityProvider } from "@json-render/react";
import { vi, test, expect } from "vitest";
import { registry } from "./registry";
import { RowsContext, PanelActionsContext } from "./rows";

vi.mock("vega-embed", () => ({ default: vi.fn(async () => ({ view: { finalize() {} } })) }));

const spec = {
  root: "grid",
  elements: {
    grid: { type: "Grid", props: { columns: 1 }, children: ["panel-0"] },
    "panel-0": { type: "Panel", props: { title: "Revenue by Region", intent: "top regions", p: 0.82, match: "strong", panelIndex: 0 }, children: ["leaf-0"] },
    "leaf-0": { type: "Table", props: { columns: ["region", "revenue"], maxRows: 200 }, children: [] },
  },
};

test("renders panel chrome, table rows and alternates", () => {
  const actions = { alternates: () => [{ id: "c07", kind: "pie", title: "Share", p: 0.41, element: spec.elements["leaf-0"] }], swap: vi.fn() };
  render(
    <RowsContext.Provider value={[{ region: "EMEA", revenue: 10 }]}>
      <PanelActionsContext.Provider value={actions}>
        <StateProvider initialState={{}}><VisibilityProvider><ActionProvider><Renderer spec={spec} registry={registry} /></ActionProvider></VisibilityProvider></StateProvider>
      </PanelActionsContext.Provider>
    </RowsContext.Provider>,
  );
  expect(screen.getByText("Revenue by Region")).toBeInTheDocument();
  expect(screen.getByText("82% match")).toBeInTheDocument();
  expect(screen.getByText("EMEA")).toBeInTheDocument();
  screen.getByRole("button", { name: /Share/ }).click();
  expect(actions.swap).toHaveBeenCalledWith(0, "c07");
});
