import { AnomalyRadarPanel } from "../components/AnomalyRadarPanel";
import { BackendHoldStateCard } from "../components/BackendHoldStateCard";
import { CandidateBoard } from "../components/CandidateBoard";
import { CheckpointHealthCard } from "../components/CheckpointHealthCard";
import { CurrentGateSummaryCard } from "../components/CurrentGateSummaryCard";
import { DemoDataBadge } from "../components/DemoDataBadge";
import { FutureRegressionGateCard } from "../components/FutureRegressionGateCard";
import { GateChecklistCard } from "../components/GateChecklistCard";
import { MarketCommandCenter } from "../components/MarketCommandCenter";
import { OperatorBreadcrumbs } from "../components/OperatorBreadcrumbs";
import { OperatorGateChecklistCard } from "../components/OperatorGateChecklistCard";
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
  getCurrentUiMode,
  getFutureRegressionGateStatus,
  getNexusSnapshot,
  getPrivateOperatorMode,
  getRegressionReadinessStatus,
  getRuntimeRegressionStatus,
  getWatchReappearanceGateStatus,
} from "../demo/nexusDataAdapter";

export function OverviewPage() {
  useHashScroll();
  const op = getPrivateOperatorMode();
  const snap = getNexusSnapshot();
  const uiMode = getCurrentUiMode();
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
          { label: "Market Command" },
        ]}
      />
      <div className="operator-banner" role="status">
        <span className="operator-banner-label">{op.label}</span>
        <span className="operator-banner-sep">·</span>
        <span>Market Intelligence · {op.audience}</span>
        <span className="operator-banner-sep">·</span>
        <span>Public SaaS: {op.publicSaas}</span>
        <DemoDataBadge />
      </div>

      <header className="page-header">
        <h1>Market Command Center</h1>
        <StatusBadge tone="hold">HOLD</StatusBadge>
        <StatusBadge tone="blocked">BLOCKED</StatusBadge>
        <DemoDataBadge />
        <p className="page-sub">
          Fintech Market Intelligence · UI mode: {uiMode} · Source: {snap.source}. READ ONLY · NOT
          INVESTMENT ADVICE · Backend HOLD · no auto-run · Stage 4.19 blocked · no Buy/Sell/Execute
        </p>
      </header>

      <MarketCommandCenter />

      <UnresolvedGateCard />
      <CurrentGateSummaryCard />

      <CandidateBoard />
      <SignalFeedPanel />
      <AnomalyRadarPanel />

      <div className="operator-section" id="gate-checklist">
        <h2 className="section-title">Checkpoint & gate</h2>
        <CheckpointHealthCard />
        <GateChecklistCard
          id="checklist-eth-watch-reappearance"
          title="ETH Watch Reappearance Checklist"
          items={ETH_WATCH_REAPPEARANCE_CHECKLIST}
          footer="All false under HOLD — wait for ETH watch conditions · no 30m · no 60m · Stage 4.19 blocked"
        />
        <GateChecklistCard
          id="checklist-short-regression-approval"
          title="Short Regression Approval Checklist"
          items={SHORT_REGRESSION_CHECKLIST}
          footer="All false under HOLD — continue wait-for-condition · 30m now: false · 60m: false · Auto-run: false · Stage 4.19 blocked"
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
