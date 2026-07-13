import { DemoDataBadge } from "../components/DemoDataBadge";
import { MembershipLockBadge } from "../components/MembershipLockBadge";
import {
  getEthConfirmationTimeline,
  getNexusSnapshot,
  getRiskEvidenceFlags,
  getSafetyStatus,
  getStage419Status,
} from "../demo/nexusDataAdapter";

export function RiskEvidencePage() {
  const f = getRiskEvidenceFlags();
  const safety = getSafetyStatus();
  const stage419 = getStage419Status();
  const snap = getNexusSnapshot();
  const ethTimeline = getEthConfirmationTimeline();
  const failureReason =
    ethTimeline?.failureReason ??
    snap.ethStatus.confirmationFailureReason ??
    "eth_followup_direction_changed";
  const ethDetail = ethTimeline?.ethDetail ?? snap.ethStatus.ethDetail ?? "LONG/BUY → NONE/NONE";

  return (
    <div>
      <header className="page-header">
        <h1>Risk & Evidence Center</h1>
        <DemoDataBadge />
        <MembershipLockBadge requiredTier="Pro" currentTier="Free" />
        <p className="page-sub">
          Safety flags only — no order / no ARM / no production controls. Private Operator
          read-only. Stage 4.19 start button absent (forbidden).
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
          <div className="k">Stage 4.19</div>
          <div className="v">{stage419.blocked ? "blocked" : "open"}</div>
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

      <section className="panel-card operator-card" style={{ marginTop: "1.25rem" }}>
        <div className="meta-row" style={{ marginTop: 0 }}>
          <h3 style={{ margin: 0 }}>ETH Follow-up Failure Risk</h3>
          <span className="demo-badge">SANITIZED</span>
          <DemoDataBadge />
        </div>
        <p>
          Confirmation failed · reason=<span className="mono">{failureReason}</span>
        </p>
        <p className="mono">Direction collapse: {ethDetail}</p>
        <div className="flag-grid" style={{ marginTop: "0.75rem" }}>
          <div className="flag-item">
            <div className="k">invalidation_breached</div>
            <div className="v">
              {String(ethTimeline?.invalidationBreached ?? false)}
            </div>
          </div>
          <div className="flag-item">
            <div className="k">mae_breached</div>
            <div className="v">{String(ethTimeline?.maeBreached ?? false)}</div>
          </div>
          <div className="flag-item">
            <div className="k">watch → follow-up</div>
            <div className="v">LONG/BUY → NONE/NONE</div>
          </div>
          <div className="flag-item">
            <div className="k">follow-up intent</div>
            <div className="v">hard_skip</div>
          </div>
        </div>
        <p className="muted" style={{ marginTop: "0.75rem" }}>
          No MAE breach · No invalidation breach · ETH graduation remains 0 · Stage 4.19 blocked
        </p>
      </section>

      <p className="muted" style={{ marginTop: "1rem" }}>
        No order · No ARM · No production · should_start_419={String(safety.shouldStart419)}
      </p>
      <p className="muted">{f.safetyLogSummary}</p>
      <p className="muted">{safety.summary}</p>
      <p className="muted">{stage419.reason}</p>
    </div>
  );
}
