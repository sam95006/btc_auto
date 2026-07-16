import { Link } from "react-router-dom";
import { ANOMALY_CONFIG } from "../market/anomalyConfig";
import { ANOMALY_TYPE_LABEL } from "../market/anomalyTypes";
import { useTopMarketAnomalies } from "../market/useMarketAnomalies";

/** Up to 3 live market anomaly summaries for homepage (MVP-22C). */
export function MarketAnomalyAlertSummary() {
  const top = useTopMarketAnomalies(3);

  return (
    <div className="market-anomaly-summary panel-card">
      <div className="anomaly-summary-head">
        <h3>Live Market Anomalies</h3>
        <Link className="deep-link" to="/anomalies">
          View all anomalies
        </Link>
      </div>
      <p className="muted anomaly-summary-note">
        Market anomaly — attention only; not a trade instruction. {ANOMALY_CONFIG.researchDisclaimer}
      </p>
      {top.length === 0 ? (
        <p className="muted">No ranked anomalies right now (Collecting or calm conditions).</p>
      ) : (
        <ul className="anomaly-summary-list">
          {top.map((a) => (
            <li key={a.id}>
              <div className="anomaly-summary-row">
                <span className="anomaly-summary-tag">Market anomaly</span>
                <strong className="mono">{a.symbol.replace("USDT", "")}</strong>
                <span>{ANOMALY_TYPE_LABEL[a.type]}</span>
                <span className={`anomaly-sev anomaly-sev-${a.severity.toLowerCase()}`}>
                  {a.severity}
                </span>
              </div>
              <p className="muted">{a.explanation}</p>
              <div className="mono muted anomaly-summary-meta">
                {a.freshness} · {new Date(a.lastSeenAt).toISOString()}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
