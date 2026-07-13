import { DemoDataBadge } from "../components/DemoDataBadge";
import { MembershipLockBadge } from "../components/MembershipLockBadge";
import { getRiskEvidenceFlags, getSafetyStatus } from "../demo/nexusDataAdapter";

export function RiskEvidencePage() {
  const f = getRiskEvidenceFlags();
  const safety = getSafetyStatus();

  return (
    <div>
      <header className="page-header">
        <h1>Risk & Evidence Center</h1>
        <DemoDataBadge />
        <MembershipLockBadge requiredTier="Pro" currentTier="Free" />
        <p className="page-sub">
          Safety flags only — no ARM or order controls. Private Operator read-only.
        </p>
      </header>
      <div className="flag-grid">
        <div className="flag-item">
          <div className="k">order_allowed</div>
          <div className="v">{String(f.orderAllowed)}</div>
        </div>
        <div className="flag-item">
          <div className="k">mock</div>
          <div className="v">{String(f.mock)}</div>
        </div>
        <div className="flag-item">
          <div className="k">ARM</div>
          <div className="v">{String(f.arm)}</div>
        </div>
        <div className="flag-item">
          <div className="k">production</div>
          <div className="v">{String(f.production)}</div>
        </div>
        <div className="flag-item">
          <div className="k">paper execution</div>
          <div className="v">{String(f.paperExecution)}</div>
        </div>
        <div className="flag-item">
          <div className="k">stage_419_readiness</div>
          <div className="v">{String(f.stage419Readiness)}</div>
        </div>
        <div className="flag-item">
          <div className="k">should_start_419</div>
          <div className="v">{String(f.shouldStart419)}</div>
        </div>
        <div className="flag-item">
          <div className="k">validator</div>
          <div className="v">{f.validatorStatus}</div>
        </div>
        <div className="flag-item">
          <div className="k">calibration</div>
          <div className="v">{f.calibrationStatus}</div>
        </div>
        <div className="flag-item">
          <div className="k">graduation</div>
          <div className="v">{f.graduationStatus}</div>
        </div>
        <div className="flag-item">
          <div className="k">provider health</div>
          <div className="v">{f.providerHealth}</div>
        </div>
        <div className="flag-item">
          <div className="k">reset</div>
          <div className="v">{f.resetStatus}</div>
        </div>
      </div>
      <p className="muted" style={{ marginTop: "1rem" }}>
        {f.safetyLogSummary}
      </p>
      <p className="muted">{safety.summary}</p>
    </div>
  );
}
