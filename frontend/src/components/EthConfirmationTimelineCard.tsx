import type { EthConfirmationTimeline } from "../types/nexusSnapshot";
import { DemoDataBadge } from "./DemoDataBadge";

function TickBlock({
  title,
  provider,
  intent,
  confidence,
  directionalBias,
  candidateSide,
  entryTrigger,
  invalidation,
  mae,
}: {
  title: string;
  provider: string;
  intent: string;
  confidence: number;
  directionalBias: string;
  candidateSide: string;
  entryTrigger: string;
  invalidation: string;
  mae: string;
}) {
  return (
    <article className="panel-card operator-card">
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h3 style={{ margin: 0 }}>{title}</h3>
        <DemoDataBadge />
      </div>
      <div className="flag-grid">
        <div className="flag-item">
          <div className="k">provider</div>
          <div className="v">{provider}</div>
        </div>
        <div className="flag-item">
          <div className="k">intent</div>
          <div className="v">{intent}</div>
        </div>
        <div className="flag-item">
          <div className="k">confidence</div>
          <div className="v">{confidence.toFixed(2)}</div>
        </div>
        <div className="flag-item">
          <div className="k">bias / side</div>
          <div className="v">
            {directionalBias}/{candidateSide}
          </div>
        </div>
        <div className="flag-item">
          <div className="k">entry_trigger</div>
          <div className="v">{entryTrigger}</div>
        </div>
        <div className="flag-item">
          <div className="k">MAE</div>
          <div className="v">{mae}</div>
        </div>
        <div className="flag-item">
          <div className="k">invalidation</div>
          <div className="v">{invalidation}</div>
        </div>
      </div>
    </article>
  );
}

export function EthConfirmationTimelineCard({
  timeline,
}: {
  timeline: EthConfirmationTimeline;
}) {
  const w = timeline.watch;
  const f = timeline.followup;
  const delta = timeline.marketContextDelta;
  const systemIssue = timeline.confirmationFailureIsSystemIssue !== false;
  const notMarket =
    timeline.confirmationFailureIsMarketValid === false ||
    timeline.failureReason === "confirmation_prompt_too_strict";

  return (
    <section className="panel-card" style={{ marginTop: "1.25rem" }}>
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h2 style={{ margin: 0, fontSize: "1.1rem" }}>
          ETH Confirmation Timeline · {timeline.symbol}
        </h2>
        <span className="demo-badge">SANITIZED</span>
        <DemoDataBadge />
      </div>
      <p className="muted">
        Sanitized snapshot · READ ONLY · NOT INVESTMENT ADVICE · No live trading
      </p>

      <div className="meta-row" style={{ marginTop: "0.5rem", gap: "0.5rem", flexWrap: "wrap" }}>
        {systemIssue ? <span className="demo-badge">SYSTEM ISSUE</span> : null}
        {notMarket ? <span className="demo-badge">NOT MARKET REVERSAL</span> : null}
      </div>

      <div className="operator-card-grid" style={{ marginTop: "0.75rem" }}>
        <TickBlock
          title="Watch tick"
          provider={w.provider}
          intent={w.intent}
          confidence={w.confidence}
          directionalBias={w.directionalBias}
          candidateSide={w.candidateSide}
          entryTrigger={w.entryTrigger}
          invalidation={w.invalidation}
          mae={w.mae}
        />
        <TickBlock
          title="Follow-up tick"
          provider={f.provider}
          intent={f.intent || "hard_skip"}
          confidence={f.confidence}
          directionalBias={f.directionalBias || "NONE"}
          candidateSide={f.candidateSide || "NONE"}
          entryTrigger={f.entryTrigger}
          invalidation={f.invalidation}
          mae={f.mae}
        />
      </div>

      {delta ? (
        <div className="panel-card operator-card" style={{ marginTop: "0.75rem" }}>
          <div className="meta-row" style={{ marginTop: 0 }}>
            <h3 style={{ margin: 0 }}>Market Context Delta</h3>
            <DemoDataBadge />
          </div>
          <div className="flag-grid">
            <div className="flag-item">
              <div className="k">price_change_pct</div>
              <div className="v">{delta.priceChangePct}</div>
            </div>
            <div className="flag-item">
              <div className="k">regime</div>
              <div className="v">
                {delta.regimeBefore} → {delta.regimeAfter}
              </div>
            </div>
            <div className="flag-item">
              <div className="k">trend_strength</div>
              <div className="v">
                {delta.trendStrengthBefore} → {delta.trendStrengthAfter}
              </div>
            </div>
            <div className="flag-item">
              <div className="k">data_quality</div>
              <div className="v">
                {delta.dataQualityBefore} → {delta.dataQualityAfter}
              </div>
            </div>
          </div>
        </div>
      ) : null}

      <div className="panel-card operator-card" style={{ marginTop: "0.75rem" }}>
        <div className="meta-row" style={{ marginTop: 0 }}>
          <h3 style={{ margin: 0 }}>Conclusion</h3>
          <DemoDataBadge />
        </div>
        <p>
          Confirmation failed · reason=
          <span className="mono">
            {timeline.failureReason || "confirmation_prompt_too_strict"}
          </span>
        </p>
        <p className="mono">
          ethDetail: {timeline.ethDetail || "LONG/BUY → NONE/NONE without market reversal"} ·
          follow-up intent=hard_skip · bias/side=NONE/NONE
        </p>
        <div className="flag-grid" style={{ marginTop: "0.5rem" }}>
          <div className="flag-item">
            <div className="k">invalidation_breached</div>
            <div className="v">{String(timeline.invalidationBreached)}</div>
          </div>
          <div className="flag-item">
            <div className="k">mae_breached</div>
            <div className="v">{String(timeline.maeBreached)}</div>
          </div>
          <div className="flag-item">
            <div className="k">market_valid</div>
            <div className="v">
              {String(timeline.confirmationFailureIsMarketValid ?? false)}
            </div>
          </div>
          <div className="flag-item">
            <div className="k">system_issue</div>
            <div className="v">
              {String(timeline.confirmationFailureIsSystemIssue ?? true)}
            </div>
          </div>
          <div className="flag-item">
            <div className="k">next</div>
            <div className="v">{timeline.nextStep || "P2D confirmation prompt review"}</div>
          </div>
        </div>
        <p className="muted" style={{ marginTop: "0.75rem" }}>
          {timeline.conclusion}
        </p>
        <p className="muted">
          Next = {timeline.nextStep || "P2D-R1 runtime regression"} · recovery=
          {timeline.recoveryRecommendation} · SYSTEM ISSUE preserved historically
        </p>
      </div>
    </section>
  );
}
