import { DemoDataBadge } from "../components/DemoDataBadge";
import { EthConfirmationTimelineCard } from "../components/EthConfirmationTimelineCard";
import { MembershipLockBadge } from "../components/MembershipLockBadge";
import { PromptRepairStatusCard } from "../components/PromptRepairStatusCard";
import { RegressionReadinessCard } from "../components/RegressionReadinessCard";
import { RuntimeRegressionStatusCard } from "../components/RuntimeRegressionStatusCard";
import {
  getEthConfirmationTimeline,
  getGraduationStatus,
  getNexusSnapshot,
  getPaperLabSummary,
  getPromptRepairStatus,
  getRegressionReadinessStatus,
  getRuntimeRegressionStatus,
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

  return (
    <div>
      <header className="page-header">
        <h1>Paper Trading Lab</h1>
        <DemoDataBadge />
        <MembershipLockBadge requiredTier="Pro" currentTier="Free" />
        <p className="page-sub">
          Read-only would_enter / would_skip counts. Regression readiness=false · ETH watch
          conditions absent · sample_market_no_edge · Stage 4.19 blocked. No paper execution from
          UI.
        </p>
      </header>
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
          <div className="k">calibration</div>
          <div className="v">{p.calibrationStatus}</div>
        </div>
        <div className="flag-item">
          <div className="k">BTC status</div>
          <div className="v">{paper.btcPassed ? "passed" : "blocked"}</div>
        </div>
        <div className="flag-item">
          <div className="k">ETH status</div>
          <div className="v">{paper.ethBlocked ? "blocked" : "open"}</div>
        </div>
        <div className="flag-item">
          <div className="k">BTC graduation</div>
          <div className="v">{p.btcGraduationCount}</div>
        </div>
        <div className="flag-item">
          <div className="k">ETH graduation</div>
          <div className="v">{p.ethGraduationCount}</div>
        </div>
        <div className="flag-item">
          <div className="k">graduation</div>
          <div className="v">{p.graduationStatus}</div>
        </div>
        <div className="flag-item">
          <div className="k">Stage 4.19</div>
          <div className="v">blocked</div>
        </div>
        <div className="flag-item">
          <div className="k">stage_419_readiness</div>
          <div className="v">{String(g.stage419Readiness)}</div>
        </div>
        <div className="flag-item">
          <div className="k">should_start_419</div>
          <div className="v">{String(g.shouldStart419)}</div>
        </div>
        <div className="flag-item">
          <div className="k">paper logger</div>
          <div className="v">{p.paperLoggerStatus}</div>
        </div>
        <div className="flag-item">
          <div className="k">next diagnostic</div>
          <div className="v">{paper.nextDiagnostic}</div>
        </div>
      </div>
      <p className="muted" style={{ marginTop: "1rem" }}>
        Why not graduated to Stage 4.19: {p.whyNotGraduated}
      </p>
      <p className="muted">
        Regression readiness=false · ETH watch conditions absent · Next diagnostic:{" "}
        {paper.nextDiagnostic} (read-only; no Stage 4.19 start; no 60m).
      </p>
      <p className="muted">{g.whyBlocked}</p>

      {ready ? <RegressionReadinessCard status={ready} /> : null}
      {runtimeReg ? <RuntimeRegressionStatusCard status={runtimeReg} /> : null}
      {promptRepair ? <PromptRepairStatusCard status={promptRepair} /> : null}
      {ethTimeline ? <EthConfirmationTimelineCard timeline={ethTimeline} /> : null}
    </div>
  );
}
