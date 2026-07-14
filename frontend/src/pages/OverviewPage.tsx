import { MarketStatusCard } from "../components/MarketStatusCard";
import { BackendHoldStateCard } from "../components/BackendHoldStateCard";
import { CheckpointHealthCard } from "../components/CheckpointHealthCard";
import { DemoDataBadge } from "../components/DemoDataBadge";
import { FutureRegressionGateCard } from "../components/FutureRegressionGateCard";
import { GateChecklistCard } from "../components/GateChecklistCard";
import { OperatorBreadcrumbs } from "../components/OperatorBreadcrumbs";
import { OperatorConsoleHero } from "../components/OperatorConsoleHero";
import { OperatorGateChecklistCard } from "../components/OperatorGateChecklistCard";
import { CurrentGateSummaryCard } from "../components/CurrentGateSummaryCard";
import { RegressionReadinessCard } from "../components/RegressionReadinessCard";
import { RuntimeRegressionStatusCard } from "../components/RuntimeRegressionStatusCard";
import { StatusBadge } from "../components/StatusBadge";
import { WatchReappearanceGateCard } from "../components/WatchReappearanceGateCard";
import { SHORT_REGRESSION_CHECKLIST } from "../demo/reportIndex";
import { useHashScroll } from "../hooks/useHashScroll";
import {
  getBackendHoldStateStatus,
  getCurrentUiMode,
  getEthConfirmationTimeline,
  getFutureRegressionGateStatus,
  getGraduationStatus,
  getLatestBackendVerdict,
  getLatestReports,
  getMarketOverview,
  getNexusSnapshot,
  getPrivateOperatorMode,
  getRegressionReadinessStatus,
  getRoundTable,
  getRuntimeRegressionStatus,
  getSafetyStatus,
  getStage419Status,
  getStageGateStatus,
  getWatchReappearanceGateStatus,
} from "../demo/nexusDataAdapter";

export function OverviewPage() {
  useHashScroll();
  const markets = getMarketOverview();
  const rt = getRoundTable();
  const op = getPrivateOperatorMode();
  const gate = getStageGateStatus();
  const safety = getSafetyStatus();
  const reports = getLatestReports();
  const snap = getNexusSnapshot();
  const grad = getGraduationStatus();
  const stage419 = getStage419Status();
  const uiMode = getCurrentUiMode();
  const latestVerdict = getLatestBackendVerdict();
  const ethTimeline = getEthConfirmationTimeline();
  const runtimeReg = getRuntimeRegressionStatus();
  const ready = getRegressionReadinessStatus();
  const watchGate = getWatchReappearanceGateStatus();
  const hold = getBackendHoldStateStatus();
  const futureGate = getFutureRegressionGateStatus();
  const ethBlocker =
    snap.ethStatus.rootCause ??
    snap.ethStatus.confirmationFailureReason ??
    ethTimeline?.failureReason ??
    "ETH watch conditions not present";
  const nextStep =
    hold?.nextAllowedAction ??
    futureGate?.nextRecommendation ??
    watchGate?.nextRecommendation ??
    ready?.nextRecommendation ??
    "wait for ETH watch conditions";

  return (
    <div className="page-stack">
      <OperatorBreadcrumbs
        crumbs={[
          { label: "Operator Console", to: "/overview" },
          { label: "Overview" },
        ]}
      />
      <div className="operator-banner" role="status">
        <span className="operator-banner-label">{op.label}</span>
        <span className="operator-banner-sep">·</span>
        <span>{op.audience}</span>
        <span className="operator-banner-sep">·</span>
        <span>Public SaaS: {op.publicSaas}</span>
        <DemoDataBadge />
      </div>

      <header className="page-header">
        <h1>Private Operator Dashboard</h1>
        <StatusBadge tone="hold">HOLD</StatusBadge>
        <StatusBadge tone="blocked">BLOCKED</StatusBadge>
        <DemoDataBadge />
        <p className="page-sub">
          Total console · UI mode: {uiMode} · Source: {snap.source}. READ ONLY · NOT INVESTMENT
          ADVICE · Backend HOLD · no auto-run · Stage 4.19 blocked.
        </p>
      </header>

      <OperatorConsoleHero nextAllowedAction={nextStep} />

      <CurrentGateSummaryCard />

      <div className="operator-section" id="gate-checklist">
        <h2 className="section-title">Checkpoint & gate</h2>
        <CheckpointHealthCard />
        <GateChecklistCard
          title="Gate Checklist Summary (next short regression)"
          items={SHORT_REGRESSION_CHECKLIST}
          footer="All false under HOLD — continue wait-for-condition · 30m now: false · 60m: false · Auto-run: false · Stage 4.19 blocked"
        />
      </div>

      <div className="operator-section">
        <h2 className="section-title">Stage · Graduation · Safety</h2>
        <div className="operator-card-grid">
          <section className="panel-card operator-card">
            <div className="meta-row" style={{ marginTop: 0 }}>
              <h3 style={{ margin: 0 }}>Stage Gate</h3>
              <StatusBadge tone="hold">HOLD</StatusBadge>
              <DemoDataBadge />
            </div>
            <p className="mono">latestBackendStage: {snap.latestBackendStage}</p>
            <p className="mono">latestVerdict: {latestVerdict}</p>
            <p className="mono">
              {gate.stageLabel} · {gate.verdict}
            </p>
            <p className="muted">
              Backend State: HOLD · Release Checkpoint: P2H · Stage 4.19: BLOCKED · Next: wait for
              ETH watch conditions · 30m now: false · 60m: false · Auto-run: false
            </p>
            <p className="muted">
              reason: <span className="mono">{ethBlocker}</span>
            </p>
            <p className="muted">Next: {nextStep}</p>
          </section>

          <section className="panel-card operator-card">
            <div className="meta-row" style={{ marginTop: 0 }}>
              <h3 style={{ margin: 0 }}>Graduation (actual-only)</h3>
              <StatusBadge tone="blocked">Stage 4.19 BLOCKED</StatusBadge>
              <DemoDataBadge />
            </div>
            <div className="flag-grid">
              <div className="flag-item">
                <div className="k">BTC graduation</div>
                <div className="v">{grad.btcGraduationCount}</div>
              </div>
              <div className="flag-item">
                <div className="k">ETH graduation</div>
                <div className="v">{grad.ethGraduationCount}</div>
              </div>
              <div className="flag-item">
                <div className="k">Stage 4.19</div>
                <div className="v">
                  <StatusBadge tone="blocked">BLOCKED</StatusBadge>
                </div>
              </div>
              <div className="flag-item">
                <div className="k">should_start_419</div>
                <div className="v">{String(stage419.shouldStart419)}</div>
              </div>
            </div>
            <p className="muted" style={{ marginTop: "0.75rem" }}>
              BTC: {snap.btcStatus.statusLabel} · ETH: {snap.ethStatus.statusLabel}
            </p>
            <p className="muted">Next: {nextStep}</p>
          </section>

          <section className="panel-card operator-card">
            <div className="meta-row" style={{ marginTop: 0 }}>
              <h3 style={{ margin: 0 }}>Safety Status</h3>
              <StatusBadge tone="pass">PASS</StatusBadge>
              <DemoDataBadge />
            </div>
            <div className="flag-grid">
              <div className="flag-item">
                <div className="k">order_allowed</div>
                <div className="v">{String(safety.orderAllowed)}</div>
              </div>
              <div className="flag-item">
                <div className="k">ARM</div>
                <div className="v">{String(safety.arm)}</div>
              </div>
              <div className="flag-item">
                <div className="k">production</div>
                <div className="v">{String(safety.production)}</div>
              </div>
              <div className="flag-item">
                <div className="k">should_start_419</div>
                <div className="v">{String(safety.shouldStart419)}</div>
              </div>
              <div className="flag-item">
                <div className="k">auto-run</div>
                <div className="v">false</div>
              </div>
              <div className="flag-item">
                <div className="k">Private Operator</div>
                <div className="v">ON</div>
              </div>
            </div>
            <p className="muted" style={{ marginTop: "0.75rem" }}>
              {safety.summary}
            </p>
          </section>

          <section className="panel-card operator-card">
            <div className="meta-row" style={{ marginTop: 0 }}>
              <h3 style={{ margin: 0 }}>Latest Reports</h3>
              <DemoDataBadge />
            </div>
            <ul className="report-list">
              {reports.map((r) => (
                <li key={r.id}>
                  <strong>{r.stageMarker}</strong> — {r.title}
                  <div className="muted">
                    {r.verdict} · {r.updatedAt}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        </div>
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

      <div className="operator-section">
        <h2 className="section-title">Markets & round table</h2>
        <div className="card-grid">
          {markets.map((m) => (
            <MarketStatusCard key={m.symbol} market={m} />
          ))}
        </div>
        <section className="panel-card" style={{ marginTop: "1.25rem" }}>
          <div className="meta-row" style={{ marginTop: 0 }}>
            <h3 style={{ margin: 0 }}>Round Table (summary)</h3>
            <DemoDataBadge />
          </div>
          <p>{rt.consensus}</p>
          <p className="muted">{rt.whyNotTradeNow}</p>
          <p className="muted">Confirmation needed: {rt.confirmationNeeded}</p>
        </section>
      </div>
    </div>
  );
}
