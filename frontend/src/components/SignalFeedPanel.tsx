import { SIGNAL_FEED } from "../demo/marketIntelligence";
import { DemoDataBadge } from "./DemoDataBadge";
import { ReadOnlyNavChip } from "./ReadOnlyNavChip";
import { StatusBadge } from "./StatusBadge";

/** Signal feed — dense rows, read-only actions only (MVP-17). */
export function SignalFeedPanel() {
  return (
    <section id="signal-feed" className="operator-section">
      <div className="meta-row" style={{ marginTop: 0, marginBottom: "0.5rem" }}>
        <h2 className="section-title" style={{ margin: 0 }}>
          Signal Feed
        </h2>
        <span className="demo-badge">SANITIZED</span>
        <span className="demo-badge">READ ONLY</span>
        <DemoDataBadge />
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        No quick order · no execution · View Evidence / Ask AI / Open Risk Card only · NOT INVESTMENT
        ADVICE
      </p>

      <div className="signal-feed-desktop table-scroll">
        <table className="intel-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Symbol</th>
              <th>Provider</th>
              <th>Intent</th>
              <th>Direction</th>
              <th>Conf</th>
              <th>Trigger</th>
              <th>Gate</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {SIGNAL_FEED.map((s) => (
              <tr key={s.id}>
                <td className="mono">{s.time}</td>
                <td className="mono">{s.symbol}</td>
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
                <td className="mono">{s.status}</td>
                <td className="ro-nav-row">
                  <ReadOnlyNavChip label="View Evidence" />
                  <ReadOnlyNavChip label="Ask AI" />
                  <ReadOnlyNavChip label="Open Risk Card" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="signal-feed-mobile">
        {SIGNAL_FEED.map((s) => (
          <article key={s.id} className="panel-card dense-card signal-mobile-card">
            <div className="meta-row" style={{ marginTop: 0 }}>
              <strong className="mono">
                {s.symbol} · {s.time}
              </strong>
              <StatusBadge tone="hold">{s.status}</StatusBadge>
            </div>
            <p className="muted">
              {s.provider} · {s.intent} · {s.direction} · gate {s.gateStatus}
            </p>
            <div className="ro-nav-row">
              <ReadOnlyNavChip label="View Evidence" />
              <ReadOnlyNavChip label="Ask AI" />
              <ReadOnlyNavChip label="Open Risk Card" />
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
