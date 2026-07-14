import { BackendHoldStateCard } from "../components/BackendHoldStateCard";
import { CheckpointHealthCard } from "../components/CheckpointHealthCard";
import { DemoDataBadge } from "../components/DemoDataBadge";
import { FutureRegressionGateCard } from "../components/FutureRegressionGateCard";
import { GateChecklistCard } from "../components/GateChecklistCard";
import { MembershipLockBadge } from "../components/MembershipLockBadge";
import { OperatorGateChecklistCard } from "../components/OperatorGateChecklistCard";
import { OperatorHoldBanner } from "../components/OperatorHoldBanner";
import { StatusBadge } from "../components/StatusBadge";
import { WatchReappearanceGateCard } from "../components/WatchReappearanceGateCard";
import { SAFETY_INVARIANTS_CHECKLIST } from "../demo/reportIndex";
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
  const f = getRiskEvidenceFlags();
  const safety = getSafetyStatus();
  const stage419 = getStage419Status();
  const snap = getNexusSnapshot();
  const ethTimeline = getEthConfirmationTimeline();
  const promptRepair = getPromptRepairStatus();
  const watchGate = getWatchReappearanceGateStatus();
  const hold = getBackendHoldStateStatus();
  const futureGate = getFutureRegressionGateStatus();
  const failureReason =
    ethTimeline?.failureReason ??
    snap.ethStatus.confirmationFailureReason ??
    "ETH watch conditions not present";
  const ethDetail =
    ethTimeline?.ethDetail ??
    snap.ethStatus.ethDetail ??
    "HOLD — wait for ETH watch/valid_watch";
  const delta = ethTimeline?.marketContextDelta;

  return (
    <div className="page-stack">
      <header className="page-header">
        <h1>Risk & Safety</h1>
        <StatusBadge tone="pass">PASS</StatusBadge>
        <StatusBadge tone="hold">HOLD</StatusBadge>
        <DemoDataBadge />
        <MembershipLockBadge requiredTier="Pro" currentTier="Free" />
        <p className="page-sub">
          Safety invariants only · READ ONLY · NOT INVESTMENT ADVICE · Backend HOLD · 30m now:
          false · 60m: false · Auto-run: false · Stage 4.19 blocked.
        </p>
      </header>

      {hold ? <OperatorHoldBanner hold={hold} /> : null}

      <CheckpointHealthCard />

      <section className="panel-card operator-card">
        <div className="meta-row" style={{ marginTop: 0 }}>
          <h3 style={{ margin: 0 }}>Safety invariants</h3>
          <StatusBadge tone="pass">PASS</StatusBadge>
          <DemoDataBadge />
        </div>
        <div className="flag-grid">
          <div className="flag-item">
            <div className="k">orders</div>
            <div className="v">false</div>
          </div>
          <div className="flag-item">
            <div className="k">mock</div>
            <div className="v">false</div>
          </div>
          <div className="flag-item">
            <div className="k">ARM</div>
            <div className="v">false</div>
          </div>
          <div className="flag-item">
            <div className="k">production</div>
            <div className="v">false</div>
          </div>
          <div className="flag-item">
            <div className="k">btc_auto</div>
            <div className="v">false</div>
          </div>
          <div className="flag-item">
            <div className="k">Stage 4.19</div>
            <div className="v">false (blocked)</div>
          </div>
          <div className="flag-item">
            <div className="k">billing/accounts/API keys</div>
            <div className="v">false</div>
          </div>
          <div className="flag-item">
            <div className="k">auto-run</div>
            <div className="v">false</div>
          </div>
        </div>
        <p className="muted" style={{ marginTop: "0.75rem" }}>
          order_allowed={String(f.orderAllowed)} · mock={String(f.mock)} · ARM={String(f.arm)} ·
          production={String(f.production)} · should_start_419={String(stage419.shouldStart419)}
        </p>
      </section>

      <GateChecklistCard
        title="Safety Invariants Checklist"
        items={SAFETY_INVARIANTS_CHECKLIST}
        footer="Safety invariants PASS · release checkpoint ready · no Stage 4.19 start button · READ ONLY"
      />

      {hold ? <BackendHoldStateCard status={hold} /> : null}
      {futureGate ? <FutureRegressionGateCard status={futureGate} /> : null}
      {watchGate ? <OperatorGateChecklistCard gate={watchGate} /> : null}
      {watchGate ? <WatchReappearanceGateCard status={watchGate} /> : null}

      <section className="panel-card operator-card">
        <div className="meta-row" style={{ marginTop: 0 }}>
          <h3 style={{ margin: 0 }}>Prompt Repair Safety</h3>
          <DemoDataBadge />
        </div>
        <p className="muted">
          P2E · sample_market_no_edge · Stage 4.19 blocked · no order / no mock / no production
        </p>
        <div className="flag-grid" style={{ marginTop: "0.75rem" }}>
          <div className="flag-item">
            <div className="k">prompt_repair_added</div>
            <div className="v">{String(promptRepair?.promptRepairAdded ?? true)}</div>
          </div>
          <div className="flag-item">
            <div className="k">needs_next_runtime_regression</div>
            <div className="v">
              {String(promptRepair?.needsNextRuntimeRegression ?? true)}
            </div>
          </div>
        </div>
      </section>

      <section className="panel-card operator-card">
        <div className="meta-row" style={{ marginTop: 0 }}>
          <h3 style={{ margin: 0 }}>ETH Confirmation System Issue (historical)</h3>
          <StatusBadge tone="wait">SYSTEM ISSUE</StatusBadge>
          <DemoDataBadge />
        </div>
        <p>
          Previous failure · reason=<span className="mono">{failureReason}</span>
        </p>
        <p className="mono">Direction collapse: {ethDetail}</p>
        {delta ? (
          <p className="muted" style={{ marginTop: "0.75rem" }}>
            Context delta: price={delta.priceChangePct}% · regime {delta.regimeBefore}→
            {delta.regimeAfter}
          </p>
        ) : null}
        <p className="muted" style={{ marginTop: "0.75rem" }}>
          {safety.summary}
        </p>
      </section>
    </div>
  );
}
