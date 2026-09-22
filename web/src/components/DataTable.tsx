import { useContext } from "react";
import { RowsContext } from "../rows";

/** A column is numeric when every value it actually has is a number, so a column
 *  of nulls or mixed values stays left-aligned rather than being falsely aligned. */
function numericColumns(rows: Record<string, unknown>[], columns: string[]): Set<string> {
  return new Set(columns.filter((c) => {
    const present = rows.map((r) => r[c]).filter((v) => v !== null && v !== undefined);
    return present.length > 0 && present.every((v) => typeof v === "number");
  }));
}

export function DataTable({ columns, maxRows }: { columns: string[]; maxRows: number }) {
  const rows = useContext(RowsContext).slice(0, maxRows);
  const numeric = numericColumns(rows, columns);
  const cls = (c: string) => (numeric.has(c) ? "num" : undefined);
  return (
    <div className="table-wrap"><table>
      <thead><tr>{columns.map((c) => <th key={c} className={cls(c)}>{c}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}>{columns.map((c) => <td key={c} className={cls(c)}>{String(r[c] ?? "")}</td>)}</tr>)}</tbody>
    </table></div>
  );
}
