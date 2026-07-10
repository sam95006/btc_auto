import type { EvidenceItem } from "../types/nexus";
import { DemoDataBadge } from "./DemoDataBadge";
import { RiskScoreBadge } from "./RiskScoreBadge";
import { SignalStatusBadge } from "./SignalStatusBadge";

export function EvidenceItemCard({ item }: { item: EvidenceItem }) {
  return (
    <article className="panel-card">
      <div className="meta-row" style={{ marginTop: 0, marginBottom: "0.5rem" }}>
        <h3 style={{ margin: 0 }}>
          {item.symbol} · {item.id}
        </h3>
        <DemoDataBadge />
      </div>
      <div className="meta-row">
        <SignalStatusBadge status={item.decision} />
        <RiskScoreBadge score={item.riskScore} />
        <span className="muted">conf {(item.confidence * 100).toFixed(0)}%</span>
      </div>
      <p>{item.reason}</p>
      <p className="muted">Data quality: {item.dataQuality}</p>
      {item.skipReason ? <p className="muted">Skip: {item.skipReason}</p> : null}
      <p className="muted mono">
        {item.timestamp} · {item.provider} · {item.stageMarker}
      </p>
      <p className="muted">Report: {item.reportLink}</p>
    </article>
  );
}
