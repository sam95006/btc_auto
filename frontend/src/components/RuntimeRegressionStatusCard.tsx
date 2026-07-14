import type { RuntimeRegressionStatus } from "../types/nexusSnapshot";
import { DemoDataBadge } from "./DemoDataBadge";

function FlagItem({ k, v }: { k: string; v: string }) {
  return (
    <div className="flag-item">
      <div className="k">{k}</div>
      <div className="v">{v}</div>
    </div>
  );
}

export function RuntimeRegressionStatusCard({
  status,
}: {
  status: RuntimeRegressionStatus;
}) {
  return (
    <section className="panel-card" style={{ marginTop: "1.25rem" }}>
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h2 style={{ margin: 0, fontSize: "1.1rem" }}>Runtime Regression Status</h2>
        <span className="demo-badge">SANITIZED</span>
        <span className="demo-badge">PARTIAL_NO_ETH_WATCH</span>
        <DemoDataBadge />
      </div>
      <p className="muted">
        Sanitized snapshot · READ ONLY · NOT INVESTMENT ADVICE · technical PASS · repair not
        validated due sample · No live trading
      </p>

      <div className="flag-grid" style={{ marginTop: "0.75rem" }}>
        <FlagItem k="technical_valid" v={String(status.technicalValid)} />
        <FlagItem k="tick_count" v={String(status.tickCount)} />
        <FlagItem k="effective_decision_count" v={String(status.effectiveDecisionCount)} />
        <FlagItem k="parse_error_count" v={String(status.parseErrorCount)} />
        <FlagItem
          k="prompt_repair_runtime_present"
          v={String(status.promptRepairRuntimePresent)}
        />
        <FlagItem
          k="previous_watch_context_seen"
          v={String(status.previousWatchContextSeen)}
        />
        <FlagItem
          k="direction_collapse_guard_seen"
          v={String(status.directionCollapseGuardSeen)}
        />
        <FlagItem k="ETH valid_watch" v={String(status.ethValidWatchCount)} />
        <FlagItem k="ETH followup_cases" v={String(status.ethFollowupCasesCount)} />
        <FlagItem k="ETH graduation" v={String(status.ethGraduationCount)} />
        <FlagItem
          k="repair_effective"
          v={String(status.ethConfirmationPromptRepairEffective)}
        />
        <FlagItem k="sample_reason" v={status.sampleInsufficientReason} />
        <FlagItem k="BTC valid_watch" v={String(status.btcValidWatchCount)} />
        <FlagItem k="BTC watch note" v={status.btcValidWatchNote} />
        <FlagItem k="BTC graduation" v={String(status.btcGraduationCount)} />
        <FlagItem
          k="btc_eth_graduation_met"
          v={String(status.actualNonShadowBtcEthGraduationMet)}
        />
        <FlagItem k="Stage 4.19" v={status.stage419Blocked ? "blocked" : "open"} />
        <FlagItem k="next" v={status.nextStep} />
      </div>

      <p className="muted" style={{ marginTop: "0.75rem" }}>
        Prompt repair runtime present, but ETH watch was not observed — repair effectiveness remains
        unvalidated. Next diagnostic = P2E.
      </p>
    </section>
  );
}
