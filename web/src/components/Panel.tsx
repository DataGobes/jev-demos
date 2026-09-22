import { useContext, type ReactNode } from "react";
import { PanelActionsContext } from "../rows";

type Props = { title: string; intent: string; p: number; match: "strong" | "weak" | "none"; panelIndex: number; children?: ReactNode };

export function Panel({ title, intent, p, match, panelIndex, children }: Props) {
  const { alternates, swap } = useContext(PanelActionsContext);
  const alts = alternates(panelIndex);
  return (
    <section className={`panel match-${match}`}>
      <header>
        {/* The intent is the question the user asked, so it reads as the panel's
            subject rather than as an aside beside the generated title. */}
        <div className="panel-heading">
          <h3>{title}</h3>
          <p className="intent">&ldquo;{intent}&rdquo;</p>
        </div>
        <div className="chips">
          {match === "none" ? <span className="chip none">no strong match</span> : <span className="chip">{Math.round(p * 100)}% match</span>}
          {match === "weak" && <span className="chip weak">weak match</span>}
        </div>
      </header>
      {children}
      {alts.length > 0 && (
        <footer>
          <span className="also">also consider</span>
          {alts.map((a) => (
            <button key={a.id} onClick={() => swap(panelIndex, a.id)}>
              {a.title}<span className="alt-p">{Math.round(a.p * 100)}%</span>
            </button>
          ))}
        </footer>
      )}
    </section>
  );
}
