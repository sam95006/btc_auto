import { ANOMALY_ROWS } from "../demo/marketIntelligence";
import { ReadOnlyNavChip } from "./ReadOnlyNavChip";
import { StatusBadge } from "./StatusBadge";

const CAT_LABEL = {
  bullish: "Bullish",
  bearish: "Bearish",
  risk: "Risk",
  provider: "Provider",
  gate: "Gate",
} as const;

/** Anomaly radar — compact cards (MVP-20). */
export function AnomalyRadarPanel() {
  const cats = ["gate", "risk", "provider", "bullish", "bearish"] as const;

  return (
    <section id="anomaly-radar" className="operator-section board-section">
      <div className="section-head">
        <h2 className="section-title" style={{ margin: 0 }}>
          Anomaly Radar
        </h2>
        <StatusBadge tone="wait">WATCH</StatusBadge>
      </div>
      <p className="muted section-lede">
        Priority anomalies under HOLD · read-only cross-links
      </p>

      <div className="anomaly-grid">
        {cats.map((cat) => {
          const rows = ANOMALY_ROWS.filter((r) => r.category === cat);
          if (rows.length === 0) return null;
          return (
            <div key={cat} className="panel-card dense-card anomaly-card">
              <h3 className="anomaly-cat">{CAT_LABEL[cat]}</h3>
              <ul className="anomaly-list">
                {rows.map((r) => (
                  <li key={r.id}>
                    <div className="fleet-card-head">
                      <strong className="mono">{r.symbol}</strong>
                      <span className="muted">{r.anomalyType}</span>
                    </div>
                    <dl className="fleet-summary compact">
                      <div>
                        <dt>First</dt>
                        <dd>{r.firstAlert}</dd>
                      </div>
                      <div>
                        <dt>Latest</dt>
                        <dd>{r.latestValue}</dd>
                      </div>
                      <div>
                        <dt>Change</dt>
                        <dd>{r.change}</dd>
                      </div>
                      <div>
                        <dt>Risk</dt>
                        <dd>{r.riskNote}</dd>
                      </div>
                    </dl>
                    <div className="ro-nav-row" style={{ marginTop: "0.35rem" }}>
                      <ReadOnlyNavChip label="Evidence" to={r.links.evidence} />
                      <ReadOnlyNavChip label="Gate" to={r.links.gate} />
                      <ReadOnlyNavChip label="Provider" to={r.links.provider} />
                      <ReadOnlyNavChip label="Risk" to={r.links.risk} />
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </section>
  );
}
