import { PROVIDER_ROUTING_POSTURE } from "../demo/providerHistory";
import { DemoDataBadge } from "./DemoDataBadge";
import { ReadOnlyNavChip } from "./ReadOnlyNavChip";
import { StatusBadge } from "./StatusBadge";

/** Routing posture facts — display only, no editor (MVP-18). */
export function ProviderRoutingPostureCard() {
  const p = PROVIDER_ROUTING_POSTURE;
  return (
    <section id="provider-routing-posture" className="panel-card dense-card">
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h3 style={{ margin: 0 }}>Provider Routing Posture</h3>
        <StatusBadge tone="hold">HOLD</StatusBadge>
        <span className="demo-badge">NO EDITOR</span>
        <DemoDataBadge />
      </div>
      <div className="flag-grid" style={{ marginTop: "0.55rem" }}>
        <div className="flag-item">
          <div className="k">BTC Cerebras-first</div>
          <div className="v">{p.cerebrasFirst}</div>
        </div>
        <div className="flag-item">
          <div className="k">Shadow → graduation</div>
          <div className="v">{p.shadowForGraduation}</div>
        </div>
        <div className="flag-item">
          <div className="k">Permanent routing change</div>
          <div className="v">{String(p.permanentRoutingChange)}</div>
        </div>
        <div className="flag-item">
          <div className="k">Next action</div>
          <div className="v">{p.nextAction}</div>
        </div>
      </div>
      <p className="muted" style={{ marginTop: "0.55rem" }}>
        {p.safetyNote}
      </p>
      <div className="ro-nav-row">
        <ReadOnlyNavChip label="View Evidence" to="/evidence?q=routing" />
        <ReadOnlyNavChip label="View Gate" to="/overview#gate-checklist" />
        <ReadOnlyNavChip label="View Runbook" />
      </div>
    </section>
  );
}
