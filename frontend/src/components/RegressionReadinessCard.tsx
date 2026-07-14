import type { RegressionReadinessStatus } from "../types/nexusSnapshot";
import { DemoDataBadge } from "./DemoDataBadge";

function FlagItem({ k, v }: { k: string; v: string }) {
  return (
    <div className="flag-item">
      <div className="k">{k}</div>
      <div className="v">{v}</div>
    </div>
  );
}

export function RegressionReadinessCard({
  status,
}: {
  status: RegressionReadinessStatus;
}) {
  return (
    <section className="panel-card" style={{ marginTop: "1.25rem" }}>
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h2 style={{ margin: 0, fontSize: "1.1rem" }}>Regression Readiness</h2>
        <span className="demo-badge">SANITIZED</span>
        <span className="demo-badge">sample_market_no_edge</span>
        <DemoDataBadge />
      </div>
      <p className="muted">
        Sanitized snapshot · READ ONLY · NOT INVESTMENT ADVICE · current readiness=false · no 60m ·
        wait for ETH watch/valid_watch · No live trading
      </p>

      <div className="flag-grid" style={{ marginTop: "0.75rem" }}>
        <FlagItem k="current readiness" v={String(status.readiness)} />
        <FlagItem k="reason" v={status.reason} />
        <FlagItem k="no_watch_root_cause" v={status.noWatchRootCause} />
        <FlagItem
          k="prompt_repair_over_conservative"
          v={String(status.promptRepairOverConservativeSuspected)}
        />
        <FlagItem k="needs_prompt_adjustment" v={String(status.needsPromptAdjustment)} />
        <FlagItem k="should_run_60m" v={String(status.shouldRun60m)} />
        <FlagItem k="wait_helper_fixed" v={String(status.waitHelperFixed)} />
        <FlagItem
          k="ETH watch conditions present"
          v={String(status.ethWatchConditionsPresent)}
        />
        <FlagItem k="Stage 4.19" v={status.stage419Blocked ? "blocked" : "open"} />
        <FlagItem k="next gate" v={status.nextGate} />
        <FlagItem k="next recommendation" v={status.nextRecommendation} />
      </div>

      <p className="muted" style={{ marginTop: "0.75rem" }}>
        Prompt repair is not over-conservative. ETH watch conditions are absent — do not run
        regression soak now. Next gate = P2F ETH Watch Reappearance Gate.
      </p>
    </section>
  );
}
