import { DemoDataBadge } from "./DemoDataBadge";
import { StatusBadge } from "./StatusBadge";
import { Link } from "react-router-dom";

/** Overview top unresolved gate under HOLD (MVP-16) — wait, not run. */
export function UnresolvedGateCard() {
  return (
    <section
      id="unresolved-gate"
      className="panel-card hold-banner"
      role="status"
      aria-label="Top unresolved gate"
    >
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h2 style={{ margin: 0, fontSize: "1.1rem" }}>Top Unresolved Gate</h2>
        <StatusBadge tone="wait">WAIT</StatusBadge>
        <StatusBadge tone="hold">HOLD</StatusBadge>
        <StatusBadge tone="blocked">Stage 4.19 BLOCKED</StatusBadge>
        <DemoDataBadge />
      </div>
      <p className="muted">
        Sanitized snapshot · READ ONLY · NOT INVESTMENT ADVICE · next action is wait, not run
      </p>
      <div className="flag-grid" style={{ marginTop: "0.75rem" }}>
        <div className="flag-item">
          <div className="k">Current unresolved gate</div>
          <div className="v">ETH watch conditions not reappeared</div>
        </div>
        <div className="flag-item">
          <div className="k">Regression now</div>
          <div className="v">false</div>
        </div>
        <div className="flag-item">
          <div className="k">60m</div>
          <div className="v">false</div>
        </div>
        <div className="flag-item">
          <div className="k">Stage 4.19</div>
          <div className="v">
            <StatusBadge tone="blocked">blocked</StatusBadge>
          </div>
        </div>
        <div className="flag-item">
          <div className="k">Next action</div>
          <div className="v">wait for ETH watch conditions</div>
        </div>
      </div>
      <p className="muted" style={{ marginBottom: 0, marginTop: "0.65rem" }}>
        Jump to{" "}
        <Link className="deep-link" to="/overview#checklist-eth-watch-reappearance">
          ETH watch reappearance checklist
        </Link>{" "}
        ·{" "}
        <Link className="deep-link" to="/evidence#doc-summaries">
          Evidence excerpts
        </Link>
      </p>
    </section>
  );
}
