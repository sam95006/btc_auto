import type { WatchReappearanceGateStatus } from "../types/nexusSnapshot";
import { DemoDataBadge } from "./DemoDataBadge";

function FlagItem({ k, v }: { k: string; v: string }) {
  return (
    <div className="flag-item">
      <div className="k">{k}</div>
      <div className="v">{v}</div>
    </div>
  );
}

export function WatchReappearanceGateCard({
  status,
}: {
  status: WatchReappearanceGateStatus;
}) {
  const c = status.conditions;
  return (
    <section className="panel-card" style={{ marginTop: "1.25rem" }}>
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h2 style={{ margin: 0, fontSize: "1.1rem" }}>ETH Watch Reappearance Gate</h2>
        <span className="demo-badge">SANITIZED</span>
        <span className="demo-badge">do_not_run_now</span>
        <DemoDataBadge />
      </div>
      <p className="muted">
        Sanitized snapshot · READ ONLY · NOT INVESTMENT ADVICE · readiness=false · do not run now ·
        no 60m · wait helper PASS · No live trading
      </p>

      <div className="flag-grid" style={{ marginTop: "0.75rem" }}>
        <FlagItem k="regression_readiness" v={String(status.regressionReadiness)} />
        <FlagItem k="do_not_run_regression_now" v={String(status.doNotRunRegressionNow)} />
        <FlagItem
          k="short_regression_may_be_justified"
          v={String(status.operatorApprovedShortRegressionMayBeJustified)}
        />
        <FlagItem k="has_eth_watch_or_valid_watch" v={String(c.hasEthWatchOrValidWatch)} />
        <FlagItem k="has_long_buy_bias" v={String(c.hasLongBuyBias)} />
        <FlagItem k="confidence_near_reference" v={String(c.confidenceNearReference)} />
        <FlagItem k="entry_trigger_present" v={String(c.entryTriggerPresent)} />
        <FlagItem k="invalidation_present" v={String(c.invalidationPresent)} />
        <FlagItem k="mae_cap_passed" v={String(c.maeCapPassed)} />
        <FlagItem k="context_quality_ok" v={String(c.contextQualityOk)} />
        <FlagItem k="regime_not_unknown" v={String(c.regimeNotUnknown)} />
        <FlagItem k="should_run_60m" v={String(status.shouldRun60m)} />
        <FlagItem k="wait_helper_robustness" v={status.waitHelperRobustnessStatus} />
        <FlagItem k="Stage 4.19" v={status.stage419Blocked ? "blocked" : "open"} />
        <FlagItem k="next" v={status.nextRecommendation} />
      </div>

      <p className="muted" style={{ marginTop: "0.75rem" }}>
        ETH watch condition checklist incomplete — do not run 30m/60m. Next condition = ETH
        watch/valid_watch reappearance with bias/side/conf/trigger/invalidation/MAE/quality.
      </p>
    </section>
  );
}
