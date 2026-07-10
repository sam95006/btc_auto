import type { MarketCard } from "../types/nexus";
import { DemoDataBadge } from "./DemoDataBadge";
import { RiskScoreBadge } from "./RiskScoreBadge";
import { SignalStatusBadge } from "./SignalStatusBadge";

export function MarketStatusCard({ market }: { market: MarketCard }) {
  const up = market.change24hPct >= 0;
  return (
    <article className="panel-card">
      <div className="meta-row" style={{ marginTop: 0, marginBottom: "0.5rem" }}>
        <h3 style={{ margin: 0 }}>{market.symbol}</h3>
        <DemoDataBadge />
      </div>
      <p className="mono" style={{ fontSize: "1.15rem", margin: "0.25rem 0" }}>
        {market.price.toLocaleString(undefined, { maximumFractionDigits: 8 })}
      </p>
      <p className={up ? "price-up" : "price-down"}>
        {up ? "+" : ""}
        {market.change24hPct.toFixed(2)}% 24h
      </p>
      <p className="muted">Regime: {market.regime}</p>
      <div className="meta-row">
        <SignalStatusBadge status={market.status} />
        <RiskScoreBadge score={market.riskScore} />
      </div>
      <p className="muted">
        {market.provider} · conf {(market.confidence * 100).toFixed(0)}% ·{" "}
        {market.lastDecisionAt}
      </p>
    </article>
  );
}
