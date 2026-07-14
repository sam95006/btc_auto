import { VALIDATION_FACTS } from "../demo/marketIntelligence";
import { DemoDataBadge } from "./DemoDataBadge";
import { StatusBadge, type StatusTone } from "./StatusBadge";

/** Validation Lab board — paper/validation posture under HOLD (MVP-17). */
export function ValidationStatusBoard() {
  return (
    <section id="validation-status-board" className="panel-card dense-card">
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h3 style={{ margin: 0 }}>Validation Status Board</h3>
        <StatusBadge tone="hold">HOLD</StatusBadge>
        <span className="demo-badge">READ ONLY</span>
        <DemoDataBadge />
      </div>
      <p className="muted">
        Validation Lab · no paper execution from UI · Stage 4.19 dossier=false · NOT INVESTMENT ADVICE
      </p>
      <div className="validation-board-grid">
        {VALIDATION_FACTS.map((f) => (
          <div key={f.id} className="validation-fact">
            <StatusBadge tone={f.tone as StatusTone}>{f.tone.toUpperCase()}</StatusBadge>
            <div className="k">{f.label}</div>
            <div className="v">{f.value}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
