import type { FutureRegressionGateStatus } from "../types/nexusSnapshot";
import { DemoDataBadge } from "./DemoDataBadge";

function FlagItem({ k, v }: { k: string; v: string }) {
  return (
    <div className="flag-item">
      <div className="k">{k}</div>
      <div className="v">{v}</div>
    </div>
  );
}

export function FutureRegressionGateCard({
  status,
}: {
  status: FutureRegressionGateStatus;
}) {
  return (
    <section className="panel-card" style={{ marginTop: "1.25rem" }}>
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h2 style={{ margin: 0, fontSize: "1.1rem" }}>Future Regression Gate Checker</h2>
        <span className="demo-badge">SANITIZED</span>
        <span className="demo-badge">manual only</span>
        <DemoDataBadge />
      </div>
      <p className="muted">
        Sanitized snapshot · READ ONLY · NOT INVESTMENT ADVICE · Future checker: manual only / no
        auto-run · No live trading
      </p>
      <div className="flag-grid" style={{ marginTop: "0.75rem" }}>
        <FlagItem k="mode" v={status.mode} />
        <FlagItem k="auto_run" v={String(status.autoRun)} />
        <FlagItem
          k="eth_watch_conditions_reappeared"
          v={String(status.ethWatchConditionsReappeared)}
        />
        <FlagItem
          k="operator_may_approve_short_regression"
          v={String(status.operatorMayApproveShortRegression)}
        />
        <FlagItem k="30m now" v={String(status.shouldRun30mNow)} />
        <FlagItem k="60m" v={String(status.shouldRun60m)} />
        <FlagItem k="Stage 4.19" v={status.stage419Blocked ? "blocked" : "open"} />
        <FlagItem k="next" v={status.nextRecommendation} />
      </div>
      <p className="muted" style={{ marginTop: "0.75rem" }}>
        Passive checker only evaluates future outputs. It never auto-starts 30m / 60m / Stage 4.19.
      </p>
    </section>
  );
}
