import type { BackendHoldStateStatus } from "../types/nexusSnapshot";
import { DemoDataBadge } from "./DemoDataBadge";

function FlagItem({ k, v }: { k: string; v: string }) {
  return (
    <div className="flag-item">
      <div className="k">{k}</div>
      <div className="v">{v}</div>
    </div>
  );
}

export function BackendHoldStateCard({ status }: { status: BackendHoldStateStatus }) {
  return (
    <section className="panel-card" style={{ marginTop: "1.25rem" }}>
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h2 style={{ margin: 0, fontSize: "1.1rem" }}>Backend Hold State</h2>
        <span className="demo-badge">SANITIZED</span>
        <span className="demo-badge">HOLD</span>
        <DemoDataBadge />
      </div>
      <p className="muted">
        Sanitized snapshot · READ ONLY · NOT INVESTMENT ADVICE · Current backend state: HOLD · not a
        failure — conditional wait · No live trading
      </p>
      <div className="flag-grid" style={{ marginTop: "0.75rem" }}>
        <FlagItem k="Current backend state" v={status.state} />
        <FlagItem k="Reason" v={status.reason} />
        <FlagItem k="Next allowed action" v={status.nextAllowedAction} />
        <FlagItem k="30m now" v={String(status.shouldRun30mNow)} />
        <FlagItem k="60m" v={String(status.shouldRun60m)} />
        <FlagItem k="Stage 4.19" v={status.stage419Blocked ? "blocked" : "open"} />
        <FlagItem
          k="Permanent routing change"
          v={String(status.routingPermanentChangeSupported)}
        />
        <FlagItem
          k="next_short_regression_allowed_now"
          v={String(status.nextShortRegressionAllowedNow)}
        />
      </div>
      <p className="muted" style={{ marginTop: "0.75rem" }}>
        Backend is waiting for ETH watch/valid_watch conditions — not stuck, not auto-running.
      </p>
    </section>
  );
}
