import { PROVIDER_INTEL_FACTS } from "../demo/marketIntelligence";
import { DemoDataBadge } from "./DemoDataBadge";
import { StatusBadge } from "./StatusBadge";

/** Provider Intelligence — routing policy facts only, no editor (MVP-17). */
export function ProviderIntelligencePanel() {
  return (
    <section id="provider-intelligence" className="panel-card dense-card">
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h3 style={{ margin: 0 }}>Provider Intelligence</h3>
        <StatusBadge tone="hold">HOLD</StatusBadge>
        <span className="demo-badge">NO EDITOR</span>
        <DemoDataBadge />
      </div>
      <p className="muted">
        Permanent routing change=false · shadow ≠ graduation · READ ONLY · NOT INVESTMENT ADVICE
      </p>
      <div className="flag-grid" style={{ marginTop: "0.65rem" }}>
        {PROVIDER_INTEL_FACTS.map((f) => (
          <div key={f.id} className="flag-item">
            <div className="k">{f.label}</div>
            <div className="v">{f.value}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
