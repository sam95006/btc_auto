import type { BackendHoldStateStatus } from "../types/nexusSnapshot";
import { DemoDataBadge } from "./DemoDataBadge";

/** Prominent HOLD posture for Private Operator overview / risk pages. */
export function OperatorHoldBanner({
  hold,
}: {
  hold: BackendHoldStateStatus;
}) {
  return (
    <section className="panel-card hold-banner" role="status" aria-label="Backend HOLD state">
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h2 style={{ margin: 0, fontSize: "1.15rem" }}>Backend State: HOLD</h2>
        <span className="demo-badge">HOLD</span>
        <span className="demo-badge">wait-for-condition</span>
        <span className="demo-badge">no auto-run</span>
        <DemoDataBadge />
      </div>
      <div className="flag-grid" style={{ marginTop: "0.75rem" }}>
        <div className="flag-item">
          <div className="k">Backend State</div>
          <div className="v">{hold.state}</div>
        </div>
        <div className="flag-item">
          <div className="k">Reason</div>
          <div className="v">{hold.reason}</div>
        </div>
        <div className="flag-item">
          <div className="k">Next allowed action</div>
          <div className="v">{hold.nextAllowedAction}</div>
        </div>
        <div className="flag-item">
          <div className="k">30m now</div>
          <div className="v">{String(hold.shouldRun30mNow)}</div>
        </div>
        <div className="flag-item">
          <div className="k">60m</div>
          <div className="v">{String(hold.shouldRun60m)}</div>
        </div>
        <div className="flag-item">
          <div className="k">Stage 4.19</div>
          <div className="v">{hold.stage419Blocked ? "blocked" : "open"}</div>
        </div>
      </div>
      <p className="muted" style={{ marginTop: "0.75rem" }}>
        Conditional wait for ETH watch conditions · not a failure · READ ONLY · NOT INVESTMENT
        ADVICE
      </p>
    </section>
  );
}
