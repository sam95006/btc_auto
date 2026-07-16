import {
  formatCompactQty,
  formatOiChange,
  labelDerivativesEvidence,
  toDerivativesContext,
} from "../market/derivativesContext";
import { formatFundingPct, fundingBand, fundingBias } from "../market/fundingConfig";
import { useLivePrice } from "../market/useLiveMarketFeed";

/**
 * Compact OI / Funding / Volume context (MVP-22B).
 * Display evidence only — not recommendation scoring.
 */
export function MarketContextPanel({
  symbol = "ETH",
  recommendation = "WAIT",
}: {
  symbol?: string;
  recommendation?: string;
}) {
  const live = useLivePrice(symbol);
  const ctx = toDerivativesContext(live);
  const evidence = labelDerivativesEvidence(ctx, recommendation);

  return (
    <section className="market-context-panel panel-card" aria-label="Market Context">
      <div className="mc-head">
        <h3>Market Context</h3>
        <span className={`mc-status tone-${(ctx?.status || "unavailable").toLowerCase()}`}>
          {ctx?.status || "UNAVAILABLE"}
        </span>
      </div>
      <div className="mc-grid">
        <div className="mc-cell">
          <div className="muted mc-k">OI (coin)</div>
          <div className="mono mc-v">{formatCompactQty(ctx?.openInterest, 3)}</div>
          <div className="muted mc-sub">
            5m {formatOiChange(ctx?.oiChange5mPct, ctx?.oiWindow.m5 || "collecting")} · evid{" "}
            {evidence.oi}
          </div>
        </div>
        <div className="mc-cell">
          <div className="muted mc-k">Funding</div>
          <div className="mono mc-v">{formatFundingPct(ctx?.fundingRate)}</div>
          <div className="muted mc-sub">
            {fundingBias(ctx?.fundingRate)} · {fundingBand(ctx?.fundingRate)}
            {ctx?.nextFundingTime
              ? ` · next ${new Date(ctx.nextFundingTime).toISOString().slice(11, 16)}Z`
              : ""}
          </div>
        </div>
        <div className="mc-cell">
          <div className="muted mc-k">Volume 24h</div>
          <div className="mono mc-v">
            {formatCompactQty(ctx?.turnover24h)} USDT
          </div>
          <div className="muted mc-sub">
            coin {formatCompactQty(ctx?.volume24h, 3)} · evid {evidence.volume}
          </div>
        </div>
      </div>
      <p className="muted mc-note">{evidence.note}</p>
      <details className="mc-details">
        <summary className="muted">OI / Funding / Volume details</summary>
        <ul className="mc-detail-list mono muted">
          <li>
            OI value (USDT): {formatCompactQty(ctx?.openInterestValue)} · units coin / USDT separated
          </li>
          <li>
            OI 1m: {formatOiChange(ctx?.oiChange1mPct, ctx?.oiWindow.m1 || "collecting")} · 15m:{" "}
            {formatOiChange(ctx?.oiChange15mPct, ctx?.oiWindow.m15 || "collecting")}
          </li>
          <li>
            Funding evid {evidence.funding} · OI evid {evidence.oi} · Volume evid {evidence.volume}
          </li>
          <li>Source: BYBIT_MAINNET_LINEAR · not in recommendation scoring</li>
        </ul>
      </details>
    </section>
  );
}
