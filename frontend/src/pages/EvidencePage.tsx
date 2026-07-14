import { EvidenceItemCard } from "../components/EvidenceItemCard";
import { DemoDataBadge } from "../components/DemoDataBadge";
import { MembershipLockBadge } from "../components/MembershipLockBadge";
import { ReportIndexCard } from "../components/ReportIndexCard";
import {
  getEthConfirmationTimeline,
  getEvidence,
  getPromptRepairStatus,
  getReportIndex,
  getRuntimeRegressionStatus,
} from "../demo/nexusDataAdapter";

export function EvidencePage() {
  const items = getEvidence();
  const ethTimeline = getEthConfirmationTimeline();
  const promptRepair = getPromptRepairStatus();
  const runtimeReg = getRuntimeRegressionStatus();
  const reportIndex = getReportIndex();
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
          ADVICE. Report index: P2D / P2D-R1 / P2E / P2F / P2G / P2H. Backend HOLD / wait-for-condition.
        </p>
      </header>

      {reportIndex.length > 0 ? <ReportIndexCard items={reportIndex} /> : null}

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
              <h3 style={{ margin: 0 }}>
                P2D repair → P2D-R1 no ETH watch → P2E sample_market_no_edge
              </h3>
              <span className="demo-badge">sample_market_no_edge</span>
              <DemoDataBadge />
            </div>
            <p className="muted">
              P2D: prompt repair added → P2D-R1: technical PASS but ETH valid_watch=0 → P2E:
              sample_market_no_edge (not prompt over-conservative). Stage 4.19 blocked · no 60m.
            </p>
            <p className="mono">
              technical_valid={String(runtimeReg?.technicalValid ?? true)} · ETH vw=
              {String(runtimeReg?.ethValidWatchCount ?? 0)} · root=sample_market_no_edge · next=
              {promptRepair?.nextStep ?? "wait_for_eth_watch_conditions_reappear_no_60m"}
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
