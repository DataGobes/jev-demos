import { useContext } from "react";
import { RowsContext } from "../rows";

export function DataTable({ columns, maxRows }: { columns: string[]; maxRows: number }) {
  const rows = useContext(RowsContext).slice(0, maxRows);
  return (
    <div className="table-wrap"><table>
      <thead><tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}>{columns.map((c) => <td key={c}>{String(r[c] ?? "")}</td>)}</tr>)}</tbody>
    </table></div>
  );
}
