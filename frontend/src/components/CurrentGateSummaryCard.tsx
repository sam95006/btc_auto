import { CURRENT_GATE_HIGHLIGHTS } from "../demo/docSummaries";
import { DemoDataBadge } from "./DemoDataBadge";
import { StatusBadge } from "./StatusBadge";

/** Overview first-line gate summary: HOLD / wait / Stage 4.19 blocked (MVP-15). */
export function CurrentGateSummaryCard() {
  return (
    <section
      id="current-gate-summary"
      className="panel-card operator-console-hero"
      role="status"
      aria-label="Current gate summary"
    >
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h2 style={{ margin: 0, fontSize: "1.1rem" }}>Current Gate Summary</h2>
        <StatusBadge tone="hold">HOLD</StatusBadge>
        <StatusBadge tone="blocked">Stage 4.19 BLOCKED</StatusBadge>
        <StatusBadge tone="wait">WAIT</StatusBadge>
        <DemoDataBadge />
      </div>
      <p className="muted">
        Sanitized snapshot · READ ONLY · NOT INVESTMENT ADVICE · top 3 operator facts · next action
        is wait, not run
      </p>
      <div className="flag-grid" style={{ marginTop: "0.75rem" }}>
        <div className="flag-item">
          <div className="k">Backend State</div>
          <div className="v">
            <StatusBadge tone="hold">HOLD</StatusBadge>
          </div>
        </div>
        <div className="flag-item">
          <div className="k">ETH watch conditions</div>
          <div className="v">not reappeared</div>
        </div>
        <div className="flag-item">
          <div className="k">Regression now</div>
          <div className="v">false</div>
        </div>
        <div className="flag-item">
          <div className="k">Stage 4.19</div>
          <div className="v">
            <StatusBadge tone="blocked">blocked</StatusBadge>
          </div>
        </div>
        <div className="flag-item">
          <div className="k">30m now</div>
          <div className="v">false</div>
        </div>
        <div className="flag-item">
          <div className="k">60m</div>
          <div className="v">false</div>
        </div>
        <div className="flag-item">
          <div className="k">Auto-run</div>
          <div className="v">false</div>
        </div>
        <div className="flag-item">
          <div className="k">Next action</div>
          <div className="v">wait for ETH watch conditions</div>
        </div>
      </div>
      <ul className="gate-highlight-list">
        {CURRENT_GATE_HIGHLIGHTS.map((h) => (
          <li key={h.id}>
            <strong>{h.title}</strong>
            <div className="muted">{h.body}</div>
          </li>
        ))}
      </ul>
    </section>
  );
}
