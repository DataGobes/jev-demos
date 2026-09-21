import { useContext } from "react";
import { RowsContext } from "../rows";

export function Kpi({ label, field }: { label: string; field: string }) {
  const value = useContext(RowsContext)[0]?.[field];
  const text = typeof value === "number" ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(value ?? "—");
  return <div className="kpi"><div className="kpi-value">{text}</div><div className="kpi-label">{label}</div></div>;
}
