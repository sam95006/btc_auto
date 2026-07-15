import { SIGNAL_FEED } from "../demo/marketIntelligence";
import { ReadOnlyNavChip } from "./ReadOnlyNavChip";
import { StatusBadge } from "./StatusBadge";

/** Signal feed — clearer rows + ghost actions (MVP-20). */
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
        No execution · Evidence / Gate / Provider / Risk only
      </p>

      <div className="signal-feed-desktop table-scroll">
        <table className="intel-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Symbol</th>
              <th>Provider</th>
              <th>Intent</th>
              <th>Dir</th>
              <th>Conf</th>
              <th>Trigger</th>
              <th>Gate</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {SIGNAL_FEED.map((s) => (
              <tr key={s.id} className="signal-row">
                <td className="mono">{s.time}</td>
                <td className="mono sym-cell">{s.symbol}</td>
                <td>{s.provider}</td>
                <td>{s.intent}</td>
                <td>{s.direction}</td>
                <td className="mono">{s.confidence ?? "—"}</td>
                <td>{s.trigger}</td>
                <td>
                  <StatusBadge tone={s.gateStatus === "WAIT" ? "wait" : "hold"}>
                    {s.gateStatus}
                  </StatusBadge>
                </td>
                <td className="mono status-cell">{s.status}</td>
                <td>
                  <div className="ro-nav-row">
                    <ReadOnlyNavChip label="Evidence" to={s.links.evidence} />
                    <ReadOnlyNavChip label="Gate" to={s.links.gate} />
                    <ReadOnlyNavChip label="Provider" to={s.links.provider} />
                    <ReadOnlyNavChip label="Risk" to={s.links.risk} />
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
              <StatusBadge tone="hold">{s.status}</StatusBadge>
            </div>
            <p className="muted">
              {s.provider} · {s.intent} · {s.direction} · gate {s.gateStatus}
            </p>
            <div className="ro-nav-row">
              <ReadOnlyNavChip label="Evidence" to={s.links.evidence} />
              <ReadOnlyNavChip label="Gate" to={s.links.gate} />
              <ReadOnlyNavChip label="Provider" to={s.links.provider} />
              <ReadOnlyNavChip label="Risk" to={s.links.risk} />
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
