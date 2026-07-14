import type { WatchReappearanceGateStatus } from "../types/nexusSnapshot";
import { DemoDataBadge } from "./DemoDataBadge";

const ROWS: { key: keyof WatchReappearanceGateStatus["conditions"]; label: string }[] = [
  { key: "hasEthWatchOrValidWatch", label: "ETH watch or valid_watch" },
  { key: "hasLongBuyBias", label: "directional_bias / side != NONE" },
  { key: "confidenceNearReference", label: "confidence >= 0.45" },
  { key: "entryTriggerPresent", label: "entry_trigger present" },
  { key: "invalidationPresent", label: "invalidation present" },
  { key: "maeCapPassed", label: "MAE cap passed" },
  { key: "contextQualityOk", label: "data_quality ok" },
  { key: "regimeNotUnknown", label: "regime not unknown" },
];

/** Visualize short-regression reappearance gate (read-only). */
export function OperatorGateChecklistCard({
  gate,
}: {
  gate: WatchReappearanceGateStatus;
}) {
  const allReady = !gate.doNotRunRegressionNow;
  return (
    <section className="panel-card" style={{ marginTop: "1.25rem" }}>
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h2 style={{ margin: 0, fontSize: "1.1rem" }}>Short-Regression Gate Checklist</h2>
        <span className="demo-badge">SANITIZED</span>
        <span className="demo-badge">{allReady ? "gate open*" : "gate closed"}</span>
        <DemoDataBadge />
      </div>
      <p className="muted">
        Sanitized snapshot · READ ONLY · NOT INVESTMENT ADVICE · All must be true before operator
        may approve short regression · even then: no auto-run · no Stage 4.19
      </p>
      <ul className="gate-checklist" style={{ marginTop: "0.75rem" }}>
        {ROWS.map(({ key, label }) => {
          const ok = Boolean(gate.conditions[key]);
          return (
            <li key={key} className={ok ? "gate-ok" : "gate-fail"}>
              <span className="gate-mark">{ok ? "✓" : "✗"}</span>
              <span>{label}</span>
              <span className="mono muted">{String(ok)}</span>
            </li>
          );
        })}
      </ul>
      <div className="flag-grid" style={{ marginTop: "0.75rem" }}>
        <div className="flag-item">
          <div className="k">do_not_run_regression_now</div>
          <div className="v">{String(gate.doNotRunRegressionNow)}</div>
        </div>
        <div className="flag-item">
          <div className="k">may_justify_short_regression</div>
          <div className="v">
            {String(gate.operatorApprovedShortRegressionMayBeJustified)}
          </div>
        </div>
        <div className="flag-item">
          <div className="k">60m</div>
          <div className="v">{String(gate.shouldRun60m)}</div>
        </div>
        <div className="flag-item">
          <div className="k">Stage 4.19</div>
          <div className="v">{gate.stage419Blocked ? "blocked" : "open"}</div>
        </div>
      </div>
      <p className="muted" style={{ marginTop: "0.75rem" }}>
        Next: {gate.nextRecommendation} · *open still requires explicit operator approval
      </p>
    </section>
  );
}
