import { SIGNAL_FEED, type SignalSeverity } from "../demo/marketIntelligence";
import { ReadOnlyNavChip } from "./ReadOnlyNavChip";
import { StatusBadge } from "./StatusBadge";

function severityTone(s: SignalSeverity): "hold" | "wait" | "blocked" | "pass" {
  if (s === "blocked") return "blocked";
  if (s === "warning") return "hold";
  if (s === "watch") return "wait";
  return "pass";
}

/** Signal feed with severity + plain meaning (MVP-21). */
export function SignalFeedPanel() {
  return (
    <section id="signal-feed" className="operator-section board-section">
      <div className="section-head">
        <h2 className="section-title" style={{ margin: 0 }}>
          Signal Feed
        </h2>
        <span className="demo-badge priority-med">SANITIZED</span>
      </div>
      <p className="muted section-lede">
        Severity + meaning for each row · no execution · Evidence / Gate links only
      </p>

      <div className="signal-feed-desktop table-scroll">
        <table className="intel-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Symbol</th>
              <th>Severity</th>
              <th>Meaning</th>
              <th>Next</th>
              <th>Links</th>
            </tr>
          </thead>
          <tbody>
            {SIGNAL_FEED.map((s) => (
              <tr key={s.id} className="signal-row">
                <td className="mono">{s.time}</td>
                <td className="mono sym-cell">{s.symbol}</td>
                <td>
                  <StatusBadge tone={severityTone(s.severity)}>{s.severity}</StatusBadge>
                </td>
                <td className="muted meaning-cell">{s.meaning}</td>
                <td>
                  <ReadOnlyNavChip
                    label={s.nextAction}
                    to={
                      s.nextAction === "View Gate"
                        ? s.links.gate
                        : s.nextAction === "View Risk"
                          ? s.links.risk
                          : s.nextAction === "View Provider"
                            ? s.links.provider
                            : s.links.evidence
                    }
                  />
                </td>
                <td>
                  <div className="ro-nav-row">
                    <ReadOnlyNavChip label="Evidence" to={s.links.evidence} />
                    <ReadOnlyNavChip label="Gate" to={s.links.gate} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="signal-feed-mobile">
        {SIGNAL_FEED.map((s) => (
          <article key={s.id} className="panel-card dense-card signal-mobile-card">
            <div className="fleet-card-head">
              <strong className="mono">
                {s.symbol} · {s.time}
              </strong>
              <StatusBadge tone={severityTone(s.severity)}>{s.severity}</StatusBadge>
            </div>
            <p className="muted">{s.meaning}</p>
            <div className="ro-nav-row">
              <ReadOnlyNavChip label={s.nextAction} to={s.links.gate} />
              <ReadOnlyNavChip label="Evidence" to={s.links.evidence} />
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
