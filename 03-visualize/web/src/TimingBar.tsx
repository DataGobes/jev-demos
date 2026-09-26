import type { AppState } from "./reducer";

export function TimingBar({ s }: { s: AppState }) {
  const t = s.timings;
  const part = (label: string, v?: number) => (v === undefined ? null : <span key={label}>{label} <b>{v}ms</b></span>);
  return (
    <div className="timing" data-testid="timing">
      {part("query", t.query)}{part("profile", t.profile)}{part("jev", s.cache === "hit" ? 0 : t.jev)}{part("render", t.render)}
      {s.usage && <span><b>{s.usage.input_tokens.toLocaleString()}</b> tok · ${s.usage.usd.toFixed(4)}</span>}
      {s.scored && <span>{s.scored} scored</span>}
      {s.cache && <span>cache: {s.cache}</span>}
      {s.rowNote && <span>{s.rowNote}</span>}
      {s.simulated && <span className="simulated" data-testid="simulated">SIMULATED</span>}
    </div>
  );
}
