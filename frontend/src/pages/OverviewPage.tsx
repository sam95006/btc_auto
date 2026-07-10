import { MarketStatusCard } from "../components/MarketStatusCard";
import { DemoDataBadge } from "../components/DemoDataBadge";
import { getMarketOverview, getRoundTable } from "../data/nexusDataAdapter";

export function OverviewPage() {
  const markets = getMarketOverview();
  const rt = getRoundTable();

  return (
    <div>
      <header className="page-header">
        <h1>Market Overview</h1>
        <DemoDataBadge />
        <p className="page-sub">
          BTC / ETH / SOL / PEPE observation cards. Research-only — not investment advice.
        </p>
      </header>
      <div className="card-grid">
        {markets.map((m) => (
          <MarketStatusCard key={m.symbol} market={m} />
        ))}
      </div>
      <section style={{ marginTop: "1.5rem" }}>
        <div className="panel-card">
          <div className="meta-row" style={{ marginTop: 0 }}>
            <h3 style={{ margin: 0 }}>Round Table (summary)</h3>
            <DemoDataBadge />
          </div>
          <p>{rt.consensus}</p>
          <p className="muted">{rt.whyNotTradeNow}</p>
          <p className="muted">Confirmation needed: {rt.confirmationNeeded}</p>
        </div>
      </section>
    </div>
  );
}
