import { BackendHoldStateCard } from "../components/BackendHoldStateCard";
import { CheckpointHealthCard } from "../components/CheckpointHealthCard";
import { DemoDataBadge } from "../components/DemoDataBadge";
import { FutureRegressionGateCard } from "../components/FutureRegressionGateCard";
import { GateChecklistCard } from "../components/GateChecklistCard";
import { OperatorBreadcrumbs } from "../components/OperatorBreadcrumbs";
import { OperatorGateChecklistCard } from "../components/OperatorGateChecklistCard";
import { OperatorHoldBanner } from "../components/OperatorHoldBanner";
import { PageSummaryCard } from "../components/PageSummaryCard";
import { RelatedArtifactLinks } from "../components/RelatedArtifactLinks";
import { SafetyInvariantGrid } from "../components/SafetyInvariantGrid";
import { StatusBadge } from "../components/StatusBadge";
import { WatchReappearanceGateCard } from "../components/WatchReappearanceGateCard";
import { WhySafeSection } from "../components/WhySafeSection";
import { RISK_SAFETY_SUMMARY } from "../demo/docSummaries";
import { RISK_RELATED_STAGES, SAFETY_INVARIANTS_CHECKLIST } from "../demo/reportIndex";
import { useHashScroll } from "../hooks/useHashScroll";
import {
  getBackendHoldStateStatus,
  getEthConfirmationTimeline,
  getFutureRegressionGateStatus,
  getNexusSnapshot,
  getPromptRepairStatus,
  getRiskEvidenceFlags,
  getSafetyStatus,
  getStage419Status,
  getWatchReappearanceGateStatus,
} from "../demo/nexusDataAdapter";

export function RiskEvidencePage() {
  useHashScroll();
  const f = getRiskEvidenceFlags();
  const safety = getSafetyStatus();
  const stage419 = getStage419Status();
  const snap = getNexusSnapshot();
  const ethTimeline = getEthConfirmationTimeline();
  const promptRepair = getPromptRepairStatus();
  const watchGate = getWatchReappearanceGateStatus();
  const hold = getBackendHoldStateStatus();
  const futureGate = getFutureRegressionGateStatus();
  const ethDetail =
    ethTimeline?.ethDetail ??
    snap.ethStatus.ethDetail ??
    "HOLD — wait for ETH watch/valid_watch";

  return (
    <div className="page-stack mi-page">
      <OperatorBreadcrumbs
        crumbs={[
          { label: "Operator Console", to: "/overview" },
          { label: "Risk" },
        ]}
      />
      <header className="page-header">
        <h1>Risk Center</h1>
        <StatusBadge tone="pass">PASS</StatusBadge>
        <StatusBadge tone="hold">HOLD</StatusBadge>
        <DemoDataBadge />
        <p className="page-sub">
          Why this console is safe · READ ONLY · NOT INVESTMENT ADVICE · Backend HOLD · Stage 4.19
          blocked
        </p>
      </header>

      {hold ? <OperatorHoldBanner hold={hold} /> : null}

      <WhySafeSection />

      <PageSummaryCard {...RISK_SAFETY_SUMMARY} />

      <SafetyInvariantGrid />

      <CheckpointHealthCard />

      <section id="safety-invariants" className="panel-card dense-card">
        <div className="meta-row" style={{ marginTop: 0 }}>
          <h3 style={{ margin: 0 }}>Safety detail</h3>
          <StatusBadge tone="pass">PASS</StatusBadge>
          <DemoDataBadge />
        </div>
        <p className="muted">
          order_allowed={String(f.orderAllowed)} · mock={String(f.mock)} · ARM={String(f.arm)} ·
          production={String(f.production)} · should_start_419={String(stage419.shouldStart419)} ·{" "}
          {safety.summary} · {ethDetail}
        </p>
        <RelatedArtifactLinks
          stages={[...RISK_RELATED_STAGES]}
          label="Related checkpoint docs (P2H-QA · P2H-REL)"
        />
      </section>

      <GateChecklistCard
        id="checklist-safety-invariants"
        title="Safety Invariants Checklist"
        items={SAFETY_INVARIANTS_CHECKLIST}
        footer="Safety invariants PASS · release checkpoint ready · no Stage 4.19 start button · READ ONLY"
      />

      {hold ? <BackendHoldStateCard status={hold} /> : null}
      {futureGate ? <FutureRegressionGateCard status={futureGate} /> : null}
      {watchGate ? <OperatorGateChecklistCard gate={watchGate} /> : null}
      {watchGate ? <WatchReappearanceGateCard status={watchGate} /> : null}

      <section className="panel-card dense-card">
        <div className="meta-row" style={{ marginTop: 0 }}>
          <h3 style={{ margin: 0 }}>Prompt Repair Safety</h3>
          <DemoDataBadge />
        </div>
        <p className="muted">
          P2E · sample_market_no_edge · Stage 4.19 blocked · no order / no mock / no production ·
          prompt_repair_added={String(promptRepair?.promptRepairAdded ?? true)}
        </p>
      </section>
    </div>
  );
}
