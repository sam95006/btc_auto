import { ANOMALY_ROWS, type DecisionRadarCategory } from "../demo/marketIntelligence";
import { ReadOnlyNavChip } from "./ReadOnlyNavChip";
import { StatusBadge } from "./StatusBadge";

const CAT_LABEL: Partial<Record<DecisionRadarCategory, string>> = {
  market: "Market signals",
  gate: "Gate blockers",
  provider: "Provider divergence",
  safety: "Safety warnings",
  risk: "Safety warnings",
  bullish: "Market signals",
  bearish: "Market signals",
};

const ORDER: DecisionRadarCategory[] = ["gate", "safety", "provider", "market"];

/** Decision Radar — impact on operator decisions (MVP-21). */
export function AnomalyRadarPanel() {
  return (
    <section id="anomaly-radar" className="operator-section board-section">
      <div className="section-head">
        <h2 className="section-title" style={{ margin: 0 }}>
          Decision Radar
        </h2>
        <StatusBadge tone="wait">WATCH</StatusBadge>
      </div>
      <p className="muted section-lede">
        What happened · why it matters · next read-only action · NOT INVESTMENT ADVICE
      </p>

      <div className="anomaly-grid decision-radar-grid">
        {ORDER.map((cat) => {
          const rows = ANOMALY_ROWS.filter(
            (r) =>
              r.category === cat ||
              (cat === "safety" && r.category === "risk") ||
              (cat === "market" && (r.category === "bullish" || r.category === "bearish")),
          );
          if (rows.length === 0) return null;
          return (
            <div key={cat} className="panel-card dense-card anomaly-card">
              <h3 className="anomaly-cat">{CAT_LABEL[cat] ?? cat}</h3>
              <ul className="anomaly-list">
                {rows.map((r) => (
                  <li key={r.id}>
                    <div className="fleet-card-head">
                      <strong className="mono">{r.symbol}</strong>
                      <span className="muted">{r.anomalyType}</span>
                    </div>
                    <p>
                      <strong>What happened:</strong> {r.whatHappened}
                    </p>
                    <p className="muted">
                      <strong>Why it matters:</strong> {r.whyItMatters}
                    </p>
                    <div className="ro-nav-row">
                      <ReadOnlyNavChip
                        label={r.nextAction}
                        to={
                          r.nextAction === "View Gate"
                            ? r.links.gate
                            : r.nextAction === "View Risk"
                              ? r.links.risk
                              : r.nextAction === "View Provider"
                                ? r.links.provider
                                : r.links.evidence
                        }
                      />
                      <ReadOnlyNavChip label="Evidence" to={r.links.evidence} />
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
