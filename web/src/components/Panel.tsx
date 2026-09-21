import { useContext, type ReactNode } from "react";
import { PanelActionsContext } from "../rows";

type Props = { title: string; intent: string; p: number; match: "strong" | "weak" | "none"; panelIndex: number; children?: ReactNode };

export function Panel({ title, intent, p, match, panelIndex, children }: Props) {
  const { alternates, swap } = useContext(PanelActionsContext);
  const alts = alternates(panelIndex);
  return (
    <section className={`panel match-${match}`}>
      <header>
        <h3>{title}</h3>
        <span className="intent">&ldquo;{intent}&rdquo;</span>
        {match === "none" ? <span className="chip none">no strong match</span> : <span className="chip">{Math.round(p * 100)}% match</span>}
        {match === "weak" && <span className="chip weak">weak match</span>}
      </header>
      {children}
      {alts.length > 0 && (
        <footer>also consider:{" "}
          {alts.map((a) => <button key={a.id} onClick={() => swap(panelIndex, a.id)}>{a.title} · {Math.round(a.p * 100)}%</button>)}
        </footer>
      )}
    </section>
  );
}
