import { AnomalyRadarPanel } from "../components/AnomalyRadarPanel";
import { BackendHoldStateCard } from "../components/BackendHoldStateCard";
import { CandidateBoard } from "../components/CandidateBoard";
import { FeatureCompletenessMap } from "../components/FeatureCompletenessMap";
import { FutureRegressionGateCard } from "../components/FutureRegressionGateCard";
import { GateChecklistCard } from "../components/GateChecklistCard";
import { HoldDecisionStrip } from "../components/HoldDecisionStrip";
import { LookFirstSection } from "../components/LookFirstSection";
import { MarketCommandCenter } from "../components/MarketCommandCenter";
import { OperatorBreadcrumbs } from "../components/OperatorBreadcrumbs";
import { OperatorGateChecklistCard } from "../components/OperatorGateChecklistCard";
import { RegressionReadinessCard } from "../components/RegressionReadinessCard";
import { RuntimeRegressionStatusCard } from "../components/RuntimeRegressionStatusCard";
import { SignalFeedPanel } from "../components/SignalFeedPanel";
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
    <div className="page-stack mi-page mvp21-overview">
      <OperatorBreadcrumbs
        crumbs={[
          { label: "Operator Console", to: "/overview" },
          { label: "Overview" },
        ]}
      />
      <div className="operator-banner compact-banner desktop-only-banner" role="status">
        <span className="operator-banner-label">{op.label}</span>
        <span className="operator-banner-sep">·</span>
        <span>Market Intelligence</span>
        <span className="operator-banner-sep">·</span>
        <span>Public SaaS: {op.publicSaas}</span>
      </div>

      {/* Mobile-first simplified stack */}
      <div className="mobile-priority-stack">
        <HoldDecisionStrip />
        <LookFirstSection />
      </div>

      <div className="desktop-mcc-block">
        <MarketCommandCenter />
      </div>

      <div className="overview-lower">
        <CandidateBoard />
        <SignalFeedPanel />
        <AnomalyRadarPanel />
        <FeatureCompletenessMap />
      </div>

      <div className="operator-section desk-secondary" id="gate-checklist">
        <h2 className="section-title">Checkpoint & gate</h2>
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

      <div className="operator-section desk-secondary">
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
