import type { FleetStatus } from "../types/nexus";
import { DemoDataBadge } from "./DemoDataBadge";
import { SignalStatusBadge } from "./SignalStatusBadge";

export function FleetCard({ fleet }: { fleet: FleetStatus }) {
  return (
    <article className="panel-card">
      <div className="meta-row" style={{ marginTop: 0, marginBottom: "0.5rem" }}>
        <h3 style={{ margin: 0 }}>{fleet.symbol} Fleet</h3>
        <DemoDataBadge />
      </div>
      <p className="muted mono">{fleet.fleetId}</p>
      <p>
        Intent: <strong>{fleet.intent}</strong>
      </p>
      <div className="meta-row">
        <SignalStatusBadge status={fleet.watchState} />
        <span className="muted">conf {(fleet.confidence * 100).toFixed(0)}%</span>
      </div>
      <p className="muted">MAE {fleet.mae}</p>
      <p className="muted">Trigger: {fleet.entryTrigger}</p>
      <p className="muted">Invalidation: {fleet.invalidation}</p>
      <p className="muted">
        Provider {fleet.provider} · {fleet.graduationStatus}
      </p>
    </article>
  );
}
