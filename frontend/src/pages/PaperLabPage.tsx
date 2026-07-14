import { BackendHoldStateCard } from "../components/BackendHoldStateCard";
import { DemoDataBadge } from "../components/DemoDataBadge";
import { EthConfirmationTimelineCard } from "../components/EthConfirmationTimelineCard";
import { FutureRegressionGateCard } from "../components/FutureRegressionGateCard";
import { GateChecklistCard } from "../components/GateChecklistCard";
import { MembershipLockBadge } from "../components/MembershipLockBadge";
import { OperatorGateChecklistCard } from "../components/OperatorGateChecklistCard";
import { OperatorHoldBanner } from "../components/OperatorHoldBanner";
import { PromptRepairStatusCard } from "../components/PromptRepairStatusCard";
import { RegressionReadinessCard } from "../components/RegressionReadinessCard";
import { RuntimeRegressionStatusCard } from "../components/RuntimeRegressionStatusCard";
import { StatusBadge } from "../components/StatusBadge";
import { WatchReappearanceGateCard } from "../components/WatchReappearanceGateCard";
import { SHORT_REGRESSION_CHECKLIST } from "../demo/reportIndex";
import {
  getBackendHoldStateStatus,
  getEthConfirmationTimeline,
  getFutureRegressionGateStatus,
  getGraduationStatus,
  getNexusSnapshot,
  getPaperLabSummary,
  getPromptRepairStatus,
  getRegressionReadinessStatus,
  getRuntimeRegressionStatus,
  getWatchReappearanceGateStatus,
} from "../demo/nexusDataAdapter";

export function PaperLabPage() {
  const p = getPaperLabSummary();
  const g = getGraduationStatus();
  const snap = getNexusSnapshot();
  const paper = snap.paperLabStatus;
  const ethTimeline = getEthConfirmationTimeline();
  const promptRepair = getPromptRepairStatus();
  const runtimeReg = getRuntimeRegressionStatus();
  const ready = getRegressionReadinessStatus();
  const watchGate = getWatchReappearanceGateStatus();
  const hold = getBackendHoldStateStatus();
  const futureGate = getFutureRegressionGateStatus();

  return (
    <div className="page-stack">
      <header className="page-header">
        <h1>Paper Trading Lab</h1>
        <StatusBadge tone="hold">HOLD</StatusBadge>
        <StatusBadge tone="wait">WAIT</StatusBadge>
        <DemoDataBadge />
        <MembershipLockBadge requiredTier="Pro" currentTier="Free" />
        <p className="page-sub">
          Validation status (read-only). Next short regression allowed now=false. Backend HOLD ·
          Stage 4.19 blocked · Auto-run: false. NOT INVESTMENT ADVICE.
        </p>
      </header>

      {hold ? <OperatorHoldBanner hold={hold} /> : null}

      <section className="panel-card operator-card">
        <div className="meta-row" style={{ marginTop: 0 }}>
          <h3 style={{ margin: 0 }}>Current validation status</h3>
          <StatusBadge tone="wait">pending</StatusBadge>
          <DemoDataBadge />
        </div>
        <div className="flag-grid">
          <div className="flag-item">
            <div className="k">BTC prior graduation evidence exists</div>
            <div className="v">
              {String(paper.btcPriorGraduationEvidenceExists ?? true)}
            </div>
          </div>
          <div className="flag-item">
            <div className="k">latest BTC regression graduation</div>
            <div className="v">
              {String(
                paper.latestBtcRegressionGraduation ??
                  runtimeReg?.btcGraduationCount ??
                  p.btcGraduationCount,
              )}
            </div>
          </div>
          <div className="flag-item">
            <div className="k">ETH prompt repair done</div>
            <div className="v">
              {String(paper.ethPromptRepairDone ?? promptRepair?.promptRepairAdded ?? true)}
            </div>
          </div>
          <div className="flag-item">
            <div className="k">ETH runtime validation</div>
            <div className="v">
              <StatusBadge tone="wait">
                {(paper.ethRuntimeValidationPending ?? true) ? "pending" : "done"}
              </StatusBadge>
            </div>
          </div>
          <div className="flag-item">
            <div className="k">next short regression allowed now</div>
            <div className="v">
              {String(paper.nextShortRegressionAllowedNow ?? false)}
            </div>
          </div>
          <div className="flag-item">
            <div className="k">Stage 4.19</div>
            <div className="v">
              <StatusBadge tone="blocked">BLOCKED</StatusBadge>
            </div>
          </div>
        </div>
      </section>

      <GateChecklistCard
        title="Next Short Regression Checklist"
        items={SHORT_REGRESSION_CHECKLIST}
        footer="next_short_regression_allowed_now=false · 30m now: false · 60m: false · Auto-run: false"
      />

      <div className="operator-section">
        <h2 className="section-title">Paper counts (read-only)</h2>
        <div className="flag-grid">
          <div className="flag-item">
            <div className="k">would_enter</div>
            <div className="v">{p.wouldEnterCount}</div>
          </div>
          <div className="flag-item">
            <div className="k">would_skip</div>
            <div className="v">{p.wouldSkipCount}</div>
          </div>
          <div className="flag-item">
            <div className="k">watchlist</div>
            <div className="v">{p.watchlistCount}</div>
          </div>
          <div className="flag-item">
            <div className="k">should_start_419</div>
            <div className="v">{String(g.shouldStart419)}</div>
          </div>
        </div>
        <p className="muted" style={{ marginTop: "1rem" }}>
          Why not graduated to Stage 4.19: {p.whyNotGraduated}
        </p>
        <p className="muted">{g.whyBlocked}</p>
      </div>

      <div className="operator-section">
        <h2 className="section-title">Hold detail</h2>
        {hold ? <BackendHoldStateCard status={hold} /> : null}
        {futureGate ? <FutureRegressionGateCard status={futureGate} /> : null}
        {watchGate ? <OperatorGateChecklistCard gate={watchGate} /> : null}
        {watchGate ? <WatchReappearanceGateCard status={watchGate} /> : null}
        {ready ? <RegressionReadinessCard status={ready} /> : null}
        {runtimeReg ? <RuntimeRegressionStatusCard status={runtimeReg} /> : null}
        {promptRepair ? <PromptRepairStatusCard status={promptRepair} /> : null}
        {ethTimeline ? <EthConfirmationTimelineCard timeline={ethTimeline} /> : null}
      </div>
    </div>
  );
}
