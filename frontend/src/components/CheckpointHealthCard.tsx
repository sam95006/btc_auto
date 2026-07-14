import { getReleaseHealth, type ReleaseHealthStatus } from "../demo/releaseHealth";
import { DemoDataBadge } from "./DemoDataBadge";

/** Compact badge for headers / Evidence report index. */
export function ReleaseHealthBadge({
  health = getReleaseHealth(),
}: {
  health?: ReleaseHealthStatus;
}) {
  return (
    <span
      className="demo-badge release-health-badge"
      title={`${health.latestReleaseCheckpoint} · HOLD · read-only`}
    >
      {health.latestReleaseCheckpoint} health PASS
    </span>
  );
}

/** Overview / Risk card for HOLD release checkpoint. */
export function CheckpointHealthCard({
  health = getReleaseHealth(),
}: {
  health?: ReleaseHealthStatus;
}) {
  return (
    <section
      id="release-checkpoint"
      className="panel-card hold-banner"
      style={{ marginTop: "1.25rem" }}
      role="status"
    >
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h2 style={{ margin: 0, fontSize: "1.1rem" }}>Release Checkpoint Health</h2>
        <ReleaseHealthBadge health={health} />
        <span className="demo-badge">HOLD</span>
        <span className="demo-badge">no auto-run</span>
        <DemoDataBadge />
      </div>
      <p className="muted">
        Sanitized snapshot · READ ONLY · NOT INVESTMENT ADVICE · Private Operator · checkpoint{" "}
        {health.latestReleaseCheckpoint}
      </p>
      <div className="flag-grid" style={{ marginTop: "0.75rem" }}>
        <div className="flag-item">
          <div className="k">Release checkpoint ready</div>
          <div className="v">{String(health.releaseCheckpointReady)}</div>
        </div>
        <div className="flag-item">
          <div className="k">Backend HOLD confirmed</div>
          <div className="v">{String(health.backendHoldStateConfirmed)}</div>
        </div>
        <div className="flag-item">
          <div className="k">UI Private Operator read-only</div>
          <div className="v">{String(health.uiPrivateOperatorReadonly)}</div>
        </div>
        <div className="flag-item">
          <div className="k">No Stage 4.19 start</div>
          <div className="v">{String(health.noStage419Start)}</div>
        </div>
        <div className="flag-item">
          <div className="k">No order path</div>
          <div className="v">{String(health.noOrderPathAdded)}</div>
        </div>
        <div className="flag-item">
          <div className="k">No ARM path</div>
          <div className="v">{String(health.noArmPathAdded)}</div>
        </div>
        <div className="flag-item">
          <div className="k">No billing / accounts</div>
          <div className="v">{String(health.noBillingOrAccounts)}</div>
        </div>
        <div className="flag-item">
          <div className="k">No auto-run</div>
          <div className="v">{String(health.noAutoRun)}</div>
        </div>
      </div>
      <p className="muted" style={{ marginTop: "0.75rem" }}>
        Next: {health.nextRecommendation} · suggested tag: {health.suggestedGitTag}
      </p>
      <p className="mono muted">{health.checkpointDocPath}</p>
    </section>
  );
}
