import { DECISION_ALERTS } from "../demo/marketDashboard";
import { ReadOnlyNavChip } from "./ReadOnlyNavChip";

const ZONES = [
  "Confirmed Breakout",
  "Waiting for Breakout",
  "Gate Warning",
  "Provider Divergence",
] as const;

/** Compact decision alerts under the boards (MVP-22). */
export function DecisionAlertsPanel() {
  return (
    <section id="decision-alerts" className="decision-alerts-panel">
      <h2 className="section-title">Decision Alerts</h2>
      <div className="alert-zones">
        {ZONES.map((zone) => {
          const rows = DECISION_ALERTS.filter((a) => a.zone === zone);
          return (
            <div key={zone} className="panel-card alert-zone">
              <h3>{zone}</h3>
              {rows.length === 0 ? (
                <p className="muted">None</p>
              ) : (
                <ul className="alert-list">
                  {rows.map((a) => (
                    <li key={a.id}>
                      <div className="alert-head">
                        <strong className="mono">{a.symbol}</strong>
                        <span className="alert-type">{a.alertType}</span>
                      </div>
                      <p className="muted">{a.meaning}</p>
                      <ReadOnlyNavChip label={a.action} to={a.actionTo} />
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
