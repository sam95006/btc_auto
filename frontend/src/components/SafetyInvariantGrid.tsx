import { SAFETY_INVARIANTS } from "../demo/marketIntelligence";
import { DemoDataBadge } from "./DemoDataBadge";
import { StatusBadge } from "./StatusBadge";

/** Compact safety invariant grid for Risk Center (MVP-17). */
export function SafetyInvariantGrid() {
  return (
    <section id="safety-invariant-grid" className="panel-card dense-card">
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h3 style={{ margin: 0 }}>Safety Invariant Grid</h3>
        <StatusBadge tone="pass">PASS</StatusBadge>
        <span className="demo-badge">READ ONLY</span>
        <DemoDataBadge />
      </div>
      <p className="muted">
        No trading controls · Stage 4.19 blocked · NOT INVESTMENT ADVICE · Risk Governor unchanged
      </p>
      <div className="safety-invariant-grid">
        {SAFETY_INVARIANTS.map((i) => (
          <div key={i.id} className={`invariant-chip${i.ok ? " ok" : " bad"}`}>
            <span className="k">{i.label}</span>
            <span className="v mono">{i.value}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
