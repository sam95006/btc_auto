import { CheckpointHealthCard, ReleaseHealthBadge } from "../components/CheckpointHealthCard";
import { DemoDataBadge } from "../components/DemoDataBadge";
import { EvidenceItemCard } from "../components/EvidenceItemCard";
import { MembershipLockBadge } from "../components/MembershipLockBadge";
import { OperatorRunbookCard } from "../components/OperatorRunbookCard";
import { PrivateReportViewerCard } from "../components/PrivateReportViewerCard";
import { ReportIndexCard } from "../components/ReportIndexCard";
import { StatusBadge } from "../components/StatusBadge";
import {
  PRIVATE_OPERATOR_REPORTS,
  PRIVATE_OPERATOR_RUNBOOKS,
} from "../demo/reportIndex";
import {
  getEthConfirmationTimeline,
  getEvidence,
  getPromptRepairStatus,
  getReportIndex,
  getRuntimeRegressionStatus,
} from "../demo/nexusDataAdapter";

export function EvidencePage() {
  const items = getEvidence();
  const ethTimeline = getEthConfirmationTimeline();
  const promptRepair = getPromptRepairStatus();
  const runtimeReg = getRuntimeRegressionStatus();
  const reportIndex = getReportIndex();
  const watch = ethTimeline?.watch;
  const followup = ethTimeline?.followup;

  return (
    <div className="page-stack">
      <header className="page-header">
        <h1>Evidence Center</h1>
        <StatusBadge tone="hold">HOLD</StatusBadge>
        <ReleaseHealthBadge />
        <DemoDataBadge />
        <MembershipLockBadge requiredTier="Pro" currentTier="Free" />
        <p className="page-sub">
          Documents & reports hub · Report Viewer · Runbook Viewer · Release Checkpoint · P2D →
          P2H-QA. READ ONLY · NOT INVESTMENT ADVICE · Backend HOLD / wait-for-condition.
        </p>
      </header>

      <div className="operator-section">
        <h2 className="section-title">Release checkpoint</h2>
        <CheckpointHealthCard />
      </div>

      <div className="operator-section">
        <h2 className="section-title">Reports (P2D → P2H-QA)</h2>
        <PrivateReportViewerCard reports={PRIVATE_OPERATOR_REPORTS} />
        {reportIndex.length > 0 ? (
          <ReportIndexCard items={reportIndex} showP2hQaHealthBadge />
        ) : null}
      </div>

      <div className="operator-section">
        <h2 className="section-title">Runbooks</h2>
        <OperatorRunbookCard runbooks={PRIVATE_OPERATOR_RUNBOOKS} />
      </div>

      {ethTimeline ? (
        <div className="operator-section">
          <h2 className="section-title">ETH evidence trail (sanitized)</h2>
          <div className="operator-card-grid">
            <article className="panel-card operator-card">
              <div className="meta-row" style={{ marginTop: 0 }}>
                <h3 style={{ margin: 0 }}>ETH Watch Evidence</h3>
                <span className="demo-badge">SANITIZED</span>
                <DemoDataBadge />
              </div>
              <p className="mono">
                {watch?.provider} · intent={watch?.intent} · conf={watch?.confidence.toFixed(2)} ·{" "}
                {watch?.directionalBias}/{watch?.candidateSide}
              </p>
              <p className="muted">
                Triggers: entry={watch?.entryTrigger} · MAE={watch?.mae} · invalidation=
                {watch?.invalidation}
              </p>
            </article>

            <article className="panel-card operator-card">
              <div className="meta-row" style={{ marginTop: 0 }}>
                <h3 style={{ margin: 0 }}>ETH Follow-up Evidence</h3>
                <StatusBadge tone="wait">SYSTEM ISSUE</StatusBadge>
                <DemoDataBadge />
              </div>
              <p className="mono">
                {followup?.provider} · intent={followup?.intent} · conf=
                {followup?.confidence.toFixed(1)} · {followup?.directionalBias}/
                {followup?.candidateSide}
              </p>
              <p className="muted">
                {ethTimeline.failureReason || "confirmation_prompt_too_strict"} ·{" "}
                {ethTimeline.ethDetail || "LONG/BUY → NONE/NONE"}
              </p>
            </article>

            <article className="panel-card operator-card">
              <div className="meta-row" style={{ marginTop: 0 }}>
                <h3 style={{ margin: 0 }}>Chain status</h3>
                <StatusBadge tone="wait">WAIT</StatusBadge>
                <DemoDataBadge />
              </div>
              <p className="muted">
                P2D repair → P2D-R1 no ETH watch → P2E sample_market_no_edge → HOLD. Stage 4.19
                blocked · 30m now: false · 60m: false · Auto-run: false.
              </p>
              <p className="mono">
                technical_valid={String(runtimeReg?.technicalValid ?? true)} · ETH vw=
                {String(runtimeReg?.ethValidWatchCount ?? 0)} · next=
                {promptRepair?.nextStep ?? "wait_for_eth_watch_conditions_reappear_no_60m"}
              </p>
            </article>
          </div>
        </div>
      ) : null}

      <div className="operator-section">
        <h2 className="section-title">Recent decision evidence</h2>
        <div className="list-stack">
          {items.map((item) => (
            <EvidenceItemCard key={item.id} item={item} />
          ))}
        </div>
      </div>
    </div>
  );
}
