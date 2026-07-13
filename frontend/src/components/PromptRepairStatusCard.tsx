import type { PromptRepairStatus } from "../types/nexusSnapshot";
import { DemoDataBadge } from "./DemoDataBadge";

function FlagItem({ k, v }: { k: string; v: string }) {
  return (
    <div className="flag-item">
      <div className="k">{k}</div>
      <div className="v">{v}</div>
    </div>
  );
}

export function PromptRepairStatusCard({
  status,
}: {
  status: PromptRepairStatus;
}) {
  return (
    <section className="panel-card" style={{ marginTop: "1.25rem" }}>
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h2 style={{ margin: 0, fontSize: "1.1rem" }}>Prompt Repair Status</h2>
        <span className="demo-badge">SANITIZED</span>
        <span className="demo-badge">prompt repair status</span>
        <DemoDataBadge />
      </div>
      <p className="muted">
        Sanitized snapshot · READ ONLY · NOT INVESTMENT ADVICE · SYSTEM ISSUE preserved
        historically · No live trading
      </p>

      <div className="flag-grid" style={{ marginTop: "0.75rem" }}>
        <FlagItem k="prompt_repair_added" v={String(status.promptRepairAdded)} />
        <FlagItem
          k="previous_watch_context_injected"
          v={String(status.previousWatchContextInjected)}
        />
        <FlagItem
          k="entry_trigger_recheck_required"
          v={String(status.entryTriggerRecheckRequired)}
        />
        <FlagItem
          k="invalidation_recheck_required"
          v={String(status.invalidationRecheckRequired)}
        />
        <FlagItem k="mae_recheck_required" v={String(status.maeRecheckRequired)} />
        <FlagItem
          k="context_continuity_check_required"
          v={String(status.contextContinuityCheckRequired)}
        />
        <FlagItem
          k="direction_collapse_guard_added"
          v={String(status.directionCollapseGuardAdded)}
        />
        <FlagItem
          k="confidence_collapse_reason_required"
          v={String(status.confidenceCollapseReasonRequired)}
        />
        <FlagItem
          k="static_expected_followup_behavior"
          v={status.staticExpectedFollowupBehavior}
        />
        <FlagItem
          k="would_prevent_unexplained_collapse"
          v={String(status.wouldPreventUnexplainedCollapse)}
        />
        <FlagItem
          k="needs_next_runtime_regression"
          v={String(status.needsNextRuntimeRegression)}
        />
        <FlagItem k="next_step" v={status.nextStep} />
      </div>

      <p className="muted" style={{ marginTop: "0.75rem" }}>
        Awaiting next runtime regression · Stage 4.19 blocked · permanent routing unsupported
      </p>
      <p className="muted">
        Next = {status.nextStep || "P2D-R1 runtime regression"} (read-only; no Stage 4.19 start)
      </p>
    </section>
  );
}
