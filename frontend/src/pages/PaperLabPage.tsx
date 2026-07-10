import { DemoDataBadge } from "../components/DemoDataBadge";
import { MembershipLockBadge } from "../components/MembershipLockBadge";
import { getPaperLabSummary } from "../demo/nexusDataAdapter";

export function PaperLabPage() {
  const p = getPaperLabSummary();

  return (
    <div>
      <header className="page-header">
        <h1>Paper Trading Lab</h1>
        <DemoDataBadge />
        <MembershipLockBadge requiredTier="Pro" currentTier="Free" />
        <p className="page-sub">
          Read-only would_enter / would_skip counts. No paper execution from UI.
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
          <div className="k">graduation</div>
          <div className="v">{p.graduationStatus}</div>
        </div>
        <div className="flag-item">
          <div className="k">paper logger</div>
          <div className="v">{p.paperLoggerStatus}</div>
        </div>
      </div>
      <p className="muted" style={{ marginTop: "1rem" }}>
        Why not graduated: {p.whyNotGraduated}
      </p>
    </div>
  );
}
