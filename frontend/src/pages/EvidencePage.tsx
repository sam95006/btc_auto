import { EvidenceItemCard } from "../components/EvidenceItemCard";
import { DemoDataBadge } from "../components/DemoDataBadge";
import { MembershipLockBadge } from "../components/MembershipLockBadge";
import {
  getEthConfirmationTimeline,
  getEvidence,
  getPromptRepairStatus,
  getRuntimeRegressionStatus,
} from "../demo/nexusDataAdapter";

export function EvidencePage() {
  const items = getEvidence();
  const ethTimeline = getEthConfirmationTimeline();
  const promptRepair = getPromptRepairStatus();
  const runtimeReg = getRuntimeRegressionStatus();
  const watch = ethTimeline?.watch;
  const followup = ethTimeline?.followup;

  return (
    <div>
      <header className="page-header">
        <h1>Evidence Vault</h1>
        <DemoDataBadge />
        <MembershipLockBadge requiredTier="Pro" currentTier="Free" />
        <p className="page-sub">
          Recent AI decisions with stage markers. Sanitized snapshot · READ ONLY · NOT INVESTMENT
          ADVICE. P2D static repair → P2D-R1 runtime insufficient sample timeline.
        </p>
      </header>

      {ethTimeline ? (
        <div className="operator-card-grid" style={{ marginBottom: "1.25rem" }}>
          <article className="panel-card operator-card">
            <div className="meta-row" style={{ marginTop: 0 }}>
              <h3 style={{ margin: 0 }}>ETH Watch Evidence</h3>
              <span className="demo-badge">SANITIZED</span>
              <DemoDataBadge />
            </div>
            <p className="mono">
              {watch?.provider} · intent={watch?.intent} · conf={watch?.confidence.toFixed(2)} ·{" "}
              {watch?.directionalBias}/{watch?.candidateSide}
            </p>
            <p className="muted">
              Triggers: entry={watch?.entryTrigger} · MAE={watch?.mae} · invalidation=
              {watch?.invalidation}
            </p>
            <p className="muted">Stage 4.18-P2D · valid_watch summary (sanitized)</p>
          </article>

          <article className="panel-card operator-card">
            <div className="meta-row" style={{ marginTop: 0 }}>
              <h3 style={{ margin: 0 }}>ETH Follow-up Evidence</h3>
              <span className="demo-badge">SYSTEM ISSUE</span>
              <DemoDataBadge />
            </div>
            <p className="mono">
              {followup?.provider} · intent={followup?.intent} · conf=
              {followup?.confidence.toFixed(1)} · {followup?.directionalBias}/
              {followup?.candidateSide}
            </p>
            <p className="muted">
              P2C issue preserved ·{" "}
              {ethTimeline.failureReason || "confirmation_prompt_too_strict"} ·{" "}
              {ethTimeline.ethDetail || "LONG/BUY → NONE/NONE without market reversal"}
            </p>
            <p className="muted">
              invalidation_breached={String(ethTimeline.invalidationBreached)} · mae_breached=
              {String(ethTimeline.maeBreached)} · market_valid=
              {String(ethTimeline.confirmationFailureIsMarketValid ?? false)} · system_issue=
              {String(ethTimeline.confirmationFailureIsSystemIssue ?? true)} · next=
              {ethTimeline.nextStep}
            </p>
          </article>

          {ethTimeline.marketContextDelta ? (
            <article className="panel-card operator-card">
              <div className="meta-row" style={{ marginTop: 0 }}>
                <h3 style={{ margin: 0 }}>ETH Market Context Delta</h3>
                <span className="demo-badge">NOT MARKET REVERSAL</span>
                <DemoDataBadge />
              </div>
              <p className="mono">
                price_change_pct={ethTimeline.marketContextDelta.priceChangePct} · regime{" "}
                {ethTimeline.marketContextDelta.regimeBefore}→
                {ethTimeline.marketContextDelta.regimeAfter}
              </p>
              <p className="muted">
                trend_strength {ethTimeline.marketContextDelta.trendStrengthBefore}→
                {ethTimeline.marketContextDelta.trendStrengthAfter} · data_quality{" "}
                {ethTimeline.marketContextDelta.dataQualityBefore}→
                {ethTimeline.marketContextDelta.dataQualityAfter}
              </p>
            </article>
          ) : null}

          <article className="panel-card operator-card">
            <div className="meta-row" style={{ marginTop: 0 }}>
              <h3 style={{ margin: 0 }}>P2D static repair → P2D-R1 runtime insufficient sample</h3>
              <span className="demo-badge">PARTIAL_NO_ETH_WATCH</span>
              <DemoDataBadge />
            </div>
            <p className="muted">
              P2C: confirmation_prompt_too_strict (SYSTEM ISSUE) → P2D: prompt repair added →
              P2D-R1: technical PASS but ETH valid_watch=0 so repair not runtime-validated
              (insufficient sample).
            </p>
            <p className="mono">
              technical_valid={String(runtimeReg?.technicalValid ?? true)} · ETH vw=
              {String(runtimeReg?.ethValidWatchCount ?? 0)} · followup=
              {String(runtimeReg?.ethFollowupCasesCount ?? 0)} · repair_effective=
              {String(runtimeReg?.ethConfirmationPromptRepairEffective ?? false)} · next=
              {runtimeReg?.nextStep ?? promptRepair?.nextStep ?? "P2E"}
            </p>
            <p className="muted">
              Stage 4.19 blocked · READ ONLY · NOT INVESTMENT ADVICE
            </p>
          </article>
        </div>
      ) : null}

      <div className="list-stack">
        {items.map((item) => (
          <EvidenceItemCard key={item.id} item={item} />
        ))}
      </div>
    </div>
  );
}
