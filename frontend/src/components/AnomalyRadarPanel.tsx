import { ANOMALY_ROWS } from "../demo/marketIntelligence";
import { DemoDataBadge } from "./DemoDataBadge";
import { Link } from "react-router-dom";
import { StatusBadge } from "./StatusBadge";

const CAT_LABEL = {
  bullish: "Bullish anomaly",
  bearish: "Bearish anomaly",
  risk: "Risk anomaly",
  provider: "Provider divergence",
  gate: "Gate warning",
} as const;

/** Anomaly radar — sanitized static alerts, documentation links only (MVP-17). */
export function AnomalyRadarPanel() {
  const cats = ["gate", "risk", "provider", "bullish", "bearish"] as const;

  return (
    <section id="anomaly-radar" className="operator-section">
      <div className="meta-row" style={{ marginTop: 0, marginBottom: "0.5rem" }}>
        <h2 className="section-title" style={{ margin: 0 }}>
          Anomaly Radar
        </h2>
        <StatusBadge tone="wait">WATCH</StatusBadge>
        <span className="demo-badge">SANITIZED</span>
        <DemoDataBadge />
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        Priority anomalies under HOLD · no chase-trade · evidence links only · NOT INVESTMENT ADVICE
      </p>

      <div className="anomaly-grid">
        {cats.map((cat) => {
          const rows = ANOMALY_ROWS.filter((r) => r.category === cat);
          if (rows.length === 0) return null;
          return (
            <div key={cat} className="panel-card dense-card">
              <h3 style={{ margin: 0, fontSize: "0.85rem" }}>{CAT_LABEL[cat]}</h3>
              <ul className="anomaly-list">
                {rows.map((r) => (
                  <li key={r.id}>
                    <div className="meta-row" style={{ marginTop: 0 }}>
                      <strong className="mono">{r.symbol}</strong>
                      <span className="muted">{r.anomalyType}</span>
                    </div>
                    <div className="dense-kv">
                      <div>
                        <span className="k">First</span>
                        <span className="v">{r.firstAlert}</span>
                      </div>
                      <div>
                        <span className="k">Latest</span>
                        <span className="v">{r.latestValue}</span>
                      </div>
                      <div>
                        <span className="k">Change</span>
                        <span className="v">{r.change}</span>
                      </div>
                      <div>
                        <span className="k">Risk</span>
                        <span className="v">{r.riskNote}</span>
                      </div>
                    </div>
                    <Link className="ro-nav-chip" to={r.evidenceHref}>
                      View Evidence
                    </Link>
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
