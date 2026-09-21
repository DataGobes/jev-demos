import { defineCatalog } from "@json-render/core";
import { schema } from "@json-render/react";
import { z } from "zod";

export const catalog = defineCatalog(schema, {
  components: {
    Grid: { props: z.object({ columns: z.number().int().min(1).max(3) }), slots: ["default"], description: "Dashboard grid" },
    Panel: {
      props: z.object({ title: z.string(), intent: z.string(), p: z.number(), match: z.enum(["strong", "weak", "none"]), panelIndex: z.number().int() }),
      slots: ["default"], description: "Framed panel with match chip and alternates",
    },
    Chart: { props: z.object({ vega: z.record(z.string(), z.unknown()) }), description: "Vega-Lite chart over the shared rows" },
    Kpi: { props: z.object({ label: z.string(), field: z.string() }), description: "Single headline number from row 0" },
    Table: { props: z.object({ columns: z.array(z.string()), maxRows: z.number().int() }), description: "Result table" },
  },
  actions: {},
});
