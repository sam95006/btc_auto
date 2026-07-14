import { CheckpointHealthCard, ReleaseHealthBadge } from "../components/CheckpointHealthCard";
import { DemoDataBadge } from "../components/DemoDataBadge";
import { EvidenceItemCard } from "../components/EvidenceItemCard";
import { MembershipLockBadge } from "../components/MembershipLockBadge";
import { DocSummaryList } from "../components/DocSummaryList";
import { OperatorBreadcrumbs } from "../components/OperatorBreadcrumbs";
import { OperatorRunbookCard } from "../components/OperatorRunbookCard";
import { PrivateReportViewerCard } from "../components/PrivateReportViewerCard";
import { RelatedArtifactLinks } from "../components/RelatedArtifactLinks";
import { ReportIndexCard } from "../components/ReportIndexCard";
import { StatusBadge } from "../components/StatusBadge";
import { getOperatorDocSummaries } from "../demo/docSummaries";
import {
  findArtifact,
  PRIVATE_OPERATOR_CHECKPOINTS,
  PRIVATE_OPERATOR_REPORTS,
  PRIVATE_OPERATOR_RUNBOOKS,
  stageAnchorId,
} from "../demo/reportIndex";
import { useHashScroll } from "../hooks/useHashScroll";
import {
  getEthConfirmationTimeline,
  getEvidence,
  getPromptRepairStatus,
  getReportIndex,
  getRuntimeRegressionStatus,
} from "../demo/nexusDataAdapter";

export function EvidencePage() {
  useHashScroll();
  const items = getEvidence();
  const ethTimeline = getEthConfirmationTimeline();
  const promptRepair = getPromptRepairStatus();
  const runtimeReg = getRuntimeRegressionStatus();
  const reportIndex = getReportIndex();
  const watch = ethTimeline?.watch;
  const followup = ethTimeline?.followup;
  const checkpoint = PRIVATE_OPERATOR_CHECKPOINTS[0];

  return (
    <div className="page-stack">
      <OperatorBreadcrumbs
        crumbs={[
          { label: "Operator Console", to: "/overview" },
          { label: "Evidence Center" },
        ]}
      />
      <header className="page-header">
        <h1>Evidence Center</h1>
        <StatusBadge tone="hold">HOLD</StatusBadge>
        <ReleaseHealthBadge />
        <DemoDataBadge />
        <MembershipLockBadge requiredTier="Pro" currentTier="Free" />
        <p className="page-sub">
          Market Intelligence data layer · MVP-16 search/filter retained · P2D → P2H-REL · READ ONLY ·
          NOT INVESTMENT ADVICE · local sanitized metadata only · no trading controls.
        </p>
      </header>

      <div className="evidence-zone-strip" aria-label="Evidence zones">
        <span className="evidence-zone-chip">1 Market / Signal</span>
        <span className="evidence-zone-chip">2 Gate / Runbook</span>
        <span className="evidence-zone-chip">3 Release / Checkpoint</span>
        <span className="evidence-zone-chip">4 UI / Product</span>
      </div>

      <div className="operator-section" id="release-checkpoint">
        <h2 className="section-title">3 · Release / Checkpoint Reports</h2>
        <CheckpointHealthCard />
        {checkpoint ? (
          <section
            className="panel-card dense-card"
            id={stageAnchorId(checkpoint.stage)}
            style={{ marginTop: "1rem" }}
          >
            <div className="meta-row" style={{ marginTop: 0 }}>
              <h3 style={{ margin: 0 }}>
                {checkpoint.stage} — {checkpoint.title}
              </h3>
              <StatusBadge tone="pass">READY</StatusBadge>
              <DemoDataBadge />
            </div>
            <p className="mono muted">{checkpoint.filePath}</p>
            <p className="muted">{checkpoint.oneLineConclusion}</p>
            <RelatedArtifactLinks artifact={checkpoint} label="Related reports / runbook" />
          </section>
        ) : null}
      </div>

      <div className="operator-section">
        <h2 className="section-title">1 · Market / Signal · Gate Reports (P2D → P2H-REL)</h2>
        <DocSummaryList
          summaries={getOperatorDocSummaries()}
          title="Static Doc Summary Viewer (search/filter retained)"
          enableFilter
        />
        <PrivateReportViewerCard reports={PRIVATE_OPERATOR_REPORTS} />
        {reportIndex.length > 0 ? (
          <ReportIndexCard items={reportIndex} showP2hQaHealthBadge />
        ) : null}
      </div>

      <div className="operator-section">
        <h2 className="section-title">2 · Gate / Runbook Reports</h2>
        <OperatorRunbookCard runbooks={PRIVATE_OPERATOR_RUNBOOKS} />
        {findArtifact("4.18-P2H-OPS") ? (
          <RelatedArtifactLinks
            artifact={findArtifact("4.18-P2H-OPS")}
            label="Runbook related checkpoint"
          />
        ) : null}
      </div>

      <div className="operator-section">
        <h2 className="section-title">4 · UI / Product · ETH trail</h2>
        {ethTimeline ? (
          <div className="operator-card-grid">
            <article className="panel-card dense-card">
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

            <article className="panel-card dense-card">
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

            <article className="panel-card dense-card">
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
        ) : (
          <p className="muted">No ETH trail in sanitized snapshot.</p>
        )}
      </div>

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
