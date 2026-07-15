import { getWorkspacePins, presetHref } from "../demo/evidencePresets";
import { DemoDataBadge } from "./DemoDataBadge";
import { StatusBadge, type StatusTone } from "./StatusBadge";
import { Link } from "react-router-dom";

/**
 * Overview pinned read-only workspace shortcuts (MVP-19).
 * ETH Watch · Stage 4.19 · Safety · Provider Routing
 */
export function OperatorWorkspacePins() {
  const pins = getWorkspacePins();
  return (
    <section id="workspace-pins" className="panel-card dense-card" aria-label="Operator workspace pins">
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h2 style={{ margin: 0, fontSize: "1.05rem" }}>Operator Workspace Pins</h2>
        <StatusBadge tone="hold">HOLD</StatusBadge>
        <span className="demo-badge">READ ONLY</span>
        <DemoDataBadge />
      </div>
      <p className="muted">
        Fixed private research shortcuts · URL navigation only · no backend · no control actions · NOT
        INVESTMENT ADVICE
      </p>
      <div className="workspace-pin-grid">
        {pins.map((p) => (
          <Link key={p.id} className="workspace-pin" to={presetHref(p)}>
            <div className="meta-row" style={{ marginTop: 0 }}>
              <strong>{p.title}</strong>
              <StatusBadge tone={p.pinTone as StatusTone}>{p.pinStatusLabel}</StatusBadge>
            </div>
            <div className="muted">{p.description}</div>
            <div className="ro-nav-row" style={{ marginTop: "0.35rem" }}>
              <span className="ro-nav-chip">Open preset</span>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
