import { defineRegistry } from "@json-render/react";
import { catalog } from "./catalog";
import { Chart } from "./components/Chart";
import { DataTable } from "./components/DataTable";
import { Kpi } from "./components/Kpi";
import { Panel } from "./components/Panel";

export const { registry } = defineRegistry(catalog, {
  components: {
    Grid: ({ props, children }) => <div className="grid" style={{ gridTemplateColumns: `repeat(${props.columns}, minmax(0, 1fr))` }}>{children}</div>,
    Panel: ({ props, children }) => <Panel {...props}>{children}</Panel>,
    Chart: ({ props }) => <Chart vega={props.vega} />,
    Kpi: ({ props }) => <Kpi label={props.label} field={props.field} />,
    Table: ({ props }) => <DataTable columns={props.columns} maxRows={props.maxRows} />,
  },
});
