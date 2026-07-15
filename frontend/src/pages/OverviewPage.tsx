import { AnomalyRadarPanel } from "../components/AnomalyRadarPanel";
import { BackendHoldStateCard } from "../components/BackendHoldStateCard";
import { CandidateBoard } from "../components/CandidateBoard";
import { CheckpointHealthCard } from "../components/CheckpointHealthCard";
import { CurrentGateSummaryCard } from "../components/CurrentGateSummaryCard";
import { FutureRegressionGateCard } from "../components/FutureRegressionGateCard";
import { GateChecklistCard } from "../components/GateChecklistCard";
import { MarketCommandCenter } from "../components/MarketCommandCenter";
import { OperatorBreadcrumbs } from "../components/OperatorBreadcrumbs";
import { OperatorGateChecklistCard } from "../components/OperatorGateChecklistCard";
import { OperatorWorkspacePins } from "../components/OperatorWorkspacePins";
import { RegressionReadinessCard } from "../components/RegressionReadinessCard";
import { RuntimeRegressionStatusCard } from "../components/RuntimeRegressionStatusCard";
import { SignalFeedPanel } from "../components/SignalFeedPanel";
import { StatusBadge } from "../components/StatusBadge";
import { UnresolvedGateCard } from "../components/UnresolvedGateCard";
import { WatchReappearanceGateCard } from "../components/WatchReappearanceGateCard";
import {
  ETH_WATCH_REAPPEARANCE_CHECKLIST,
  SHORT_REGRESSION_CHECKLIST,
  STAGE_419_DOSSIER_CHECKLIST,
} from "../demo/reportIndex";
import { useHashScroll } from "../hooks/useHashScroll";
import {
  getBackendHoldStateStatus,
  getFutureRegressionGateStatus,
  getPrivateOperatorMode,
  getRegressionReadinessStatus,
  getRuntimeRegressionStatus,
  getWatchReappearanceGateStatus,
} from "../demo/nexusDataAdapter";

export function OverviewPage() {
  useHashScroll();
  const op = getPrivateOperatorMode();
  const runtimeReg = getRuntimeRegressionStatus();
  const ready = getRegressionReadinessStatus();
  const watchGate = getWatchReappearanceGateStatus();
  const hold = getBackendHoldStateStatus();
  const futureGate = getFutureRegressionGateStatus();

  return (
    <div className="page-stack mi-page">
      <OperatorBreadcrumbs
        crumbs={[
          { label: "Operator Console", to: "/overview" },
          { label: "Overview" },
        ]}
      />
      <div className="operator-banner compact-banner" role="status">
        <span className="operator-banner-label">{op.label}</span>
        <span className="operator-banner-sep">·</span>
        <span>Market Intelligence</span>
        <span className="operator-banner-sep">·</span>
        <span>Public SaaS: {op.publicSaas}</span>
      </div>

      <header className="page-header">
        <h1>Overview</h1>
        <StatusBadge tone="hold">HOLD</StatusBadge>
        <StatusBadge tone="blocked">BLOCKED</StatusBadge>
        <p className="page-sub">
          Fintech Market Intelligence · READ ONLY · NOT INVESTMENT ADVICE · Backend HOLD · Stage
          4.19 blocked
        </p>
      </header>

      <MarketCommandCenter />

      <OperatorWorkspacePins />

      <div className="overview-lower">
        <UnresolvedGateCard />
        <CurrentGateSummaryCard />
        <CandidateBoard />
        <SignalFeedPanel />
        <AnomalyRadarPanel />
      </div>

      <div className="operator-section" id="gate-checklist">
        <h2 className="section-title">Checkpoint & gate</h2>
        <CheckpointHealthCard />
        <span id="stage-419-dossier" className="anchor-alias" />
        <GateChecklistCard
          id="checklist-eth-watch-reappearance"
          title="ETH Watch Reappearance Checklist"
          items={ETH_WATCH_REAPPEARANCE_CHECKLIST}
          footer="All false under HOLD — wait for ETH watch · no 30m · no 60m · Stage 4.19 blocked"
        />
        <GateChecklistCard
          id="checklist-short-regression-approval"
          title="Short Regression Approval Checklist"
          items={SHORT_REGRESSION_CHECKLIST}
          footer="All false under HOLD — wait-for-condition · 30m now: false · 60m: false · Auto-run: false"
        />
        <GateChecklistCard
          id="checklist-stage-419-dossier"
          title="Stage 4.19 Dossier Checklist"
          items={STAGE_419_DOSSIER_CHECKLIST}
          footer="Dossier not started · needs actual non-shadow BTC + ETH graduation · no Stage 4.19 start button"
        />
      </div>

      <div className="operator-section">
        <h2 className="section-title">Hold detail (secondary)</h2>
        {hold ? <BackendHoldStateCard status={hold} /> : null}
        {futureGate ? <FutureRegressionGateCard status={futureGate} /> : null}
        {watchGate ? <OperatorGateChecklistCard gate={watchGate} /> : null}
        {watchGate ? <WatchReappearanceGateCard status={watchGate} /> : null}
        {ready ? <RegressionReadinessCard status={ready} /> : null}
        {runtimeReg ? <RuntimeRegressionStatusCard status={runtimeReg} /> : null}
      </div>
    </div>
  );
}
