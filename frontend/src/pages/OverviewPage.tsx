import { MarketStatusCard } from "../components/MarketStatusCard";
import { DemoDataBadge } from "../components/DemoDataBadge";
import {
  getCurrentUiMode,
  getGraduationStatus,
  getLatestBackendVerdict,
  getLatestReports,
  getMarketOverview,
  getNexusSnapshot,
  getPrivateOperatorMode,
  getRoundTable,
  getSafetyStatus,
  getStage419Status,
  getStageGateStatus,
} from "../demo/nexusDataAdapter";

export function OverviewPage() {
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

  return (
    <div>
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
        <DemoDataBadge />
        <p className="page-sub">
          Read-only research overview · UI mode: {uiMode} · Source: {snap.source}. Not investment
          advice.
        </p>
      </header>

      <div className="operator-card-grid">
        <section className="panel-card operator-card">
          <div className="meta-row" style={{ marginTop: 0 }}>
            <h3 style={{ margin: 0 }}>Stage Gate</h3>
            <DemoDataBadge />
          </div>
          <p className="mono">
            latestBackendStage: {snap.latestBackendStage}
          </p>
          <p className="mono">
            latestVerdict: {latestVerdict}
          </p>
          <p className="mono">
            {gate.stageLabel} · {gate.verdict}
          </p>
          <p>
            <span className="muted">P2A:</span> {gate.p2aStatus}
          </p>
          <p className="muted">{gate.latestGate}</p>
          <p className="muted">{gate.note}</p>
        </section>

        <section className="panel-card operator-card">
          <div className="meta-row" style={{ marginTop: 0 }}>
            <h3 style={{ margin: 0 }}>Graduation (actual-only)</h3>
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
              <div className="v">{stage419.blocked ? "blocked" : "open"}</div>
            </div>
            <div className="flag-item">
              <div className="k">should_start_419</div>
              <div className="v">{String(stage419.shouldStart419)}</div>
            </div>
          </div>
          <p className="muted" style={{ marginTop: "0.75rem" }}>
            BTC: {snap.btcStatus.statusLabel} · ETH: {snap.ethStatus.statusLabel}
            {snap.ethStatus.rootCause ? ` · root cause=${snap.ethStatus.rootCause}` : ""}
          </p>
        </section>

        <section className="panel-card operator-card">
          <div className="meta-row" style={{ marginTop: 0 }}>
            <h3 style={{ margin: 0 }}>Safety Status</h3>
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
              <div className="k">stage_419_readiness</div>
              <div className="v">{String(safety.stage419Readiness)}</div>
            </div>
            <div className="flag-item">
              <div className="k">should_start_419</div>
              <div className="v">{String(safety.shouldStart419)}</div>
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

      <div className="card-grid" style={{ marginTop: "1.25rem" }}>
        {markets.map((m) => (
          <MarketStatusCard key={m.symbol} market={m} />
        ))}
      </div>

      <section style={{ marginTop: "1.5rem" }}>
        <div className="panel-card">
          <div className="meta-row" style={{ marginTop: 0 }}>
            <h3 style={{ margin: 0 }}>Round Table (summary)</h3>
            <DemoDataBadge />
          </div>
          <p>{rt.consensus}</p>
          <p className="muted">{rt.whyNotTradeNow}</p>
          <p className="muted">Confirmation needed: {rt.confirmationNeeded}</p>
        </div>
      </section>
    </div>
  );
}
