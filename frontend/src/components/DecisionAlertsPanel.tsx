import { DECISION_ALERTS } from "../demo/marketDashboard";
import { formatUsd } from "../market/freshness";
import { useLivePrice } from "../market/useLiveMarketFeed";
import { ReadOnlyNavChip } from "./ReadOnlyNavChip";

const ZONES = [
  "Confirmed Breakout",
  "Waiting for Breakout",
  "Gate Warning",
  "Provider Divergence",
] as const;

function AlertItem({
  a,
}: {
  a: (typeof DECISION_ALERTS)[number];
}) {
  const live = useLivePrice(a.symbol);
  const current = live?.lastPrice;
  const trigger = a.triggerPrice;
  const distance =
    current != null && trigger != null && trigger !== 0
      ? ((current - trigger) / trigger) * 100
      : null;

  return (
    <li>
      <div className="alert-head">
        <strong className="mono">{a.symbol}</strong>
        <span className="alert-type">{a.alertType}</span>
      </div>
      <p className="muted">{a.meaning}</p>
      <div className="alert-meta mono muted">
        Trigger {a.triggerTime ? new Date(a.triggerTime).toISOString() : "—"} · TrigPx{" "}
        {formatUsd(trigger)} · Now {formatUsd(current)} · Dist{" "}
        {distance == null ? "—" : `${distance >= 0 ? "+" : ""}${distance.toFixed(2)}%`} ·{" "}
        {a.valid ? "Valid" : "Expired"}
      </div>
      <ReadOnlyNavChip label={a.action} to={a.actionTo} />
    </li>
  );
}

/** Compact decision alerts under the boards (MVP-22 / 22A). */
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
                    <AlertItem key={a.id} a={a} />
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
