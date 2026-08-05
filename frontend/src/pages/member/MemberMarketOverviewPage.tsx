import { Link } from "react-router-dom";
import { MemberPageChrome } from "../../member/MemberPageChrome";
import { marketOverviewCards } from "../../member/demoCatalog";

export function MemberMarketOverviewPage() {
  return (
    <MemberPageChrome
      title="Market Overview"
      subtitle="Public context snapshots and system freshness · not a trading blotter"
    >
      <div className="member-card-grid">
        {marketOverviewCards.map((card) => (
          <article key={card.id} className="member-panel member-market-card">
            <div className="member-card-meta">
              <h2>{card.label}</h2>
              <span className="member-chip">{card.freshness}</span>
            </div>
            <p className="member-metric-value">{card.value}</p>
            <p className="muted sm">{card.hint}</p>
          </article>
        ))}
      </div>
      <p className="muted sm">
        Need Decisions? <Link to="/decisions">Open Decision Feed</Link>
      </p>
    </MemberPageChrome>
  );
}
