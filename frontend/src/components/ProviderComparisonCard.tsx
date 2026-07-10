import type { ProviderShadowSummary } from "../types/nexus";
import { DemoDataBadge } from "./DemoDataBadge";

export function ProviderComparisonCard({
  summary,
}: {
  summary: ProviderShadowSummary;
}) {
  return (
    <article className="panel-card">
      <div className="meta-row" style={{ marginTop: 0, marginBottom: "0.5rem" }}>
        <h3 style={{ margin: 0 }}>Provider Shadow Compare</h3>
        <DemoDataBadge />
      </div>
      <p>
        Actual: <strong>{summary.actualProvider}</strong>
      </p>
      <p>
        Shadow: <strong>{summary.shadowProvider}</strong>
      </p>
      <p className="muted">Divergence: {summary.divergence}</p>
      <p className="muted">
        Comparable: {summary.comparable ? "yes" : "no"}
      </p>
      <p>{summary.notes}</p>
      <div className="flag-grid" style={{ marginTop: "0.75rem" }}>
        <div className="flag-item">
          <div className="k">Shadow → paper</div>
          <div className="v">excluded</div>
        </div>
        <div className="flag-item">
          <div className="k">Shadow → calibration</div>
          <div className="v">excluded</div>
        </div>
        <div className="flag-item">
          <div className="k">Shadow → graduation</div>
          <div className="v">excluded</div>
        </div>
        <div className="flag-item">
          <div className="k">Stage 4.19</div>
          <div className="v">must not affect</div>
        </div>
      </div>
    </article>
  );
}
