import { Link } from "react-router-dom";
import { MemberPageChrome } from "../../member/MemberPageChrome";
import { MemberUxStateChip } from "../../member/MemberUxStateChip";
import { freshnessToUxState } from "../../member/uxStates";
import { BoundLiveValue, useLiveBindings } from "../../public_v2_live_binding";

/**
 * Market Overview — PUB2-B live lineage + PUB2-C UX chips + PUB2-J i18n chrome.
 */
export function MemberMarketOverviewPage() {
  const { slot, loading } = useLiveBindings();
  const cards = [
    { binding: slot("market.overview_btc_card", "price"), label: "BTC last" },
    { binding: slot("market.overview_eth_card", "price"), label: "ETH last" },
    { binding: slot("market.freshness_card", "freshness"), label: "Feed freshness" },
    {
      binding: slot("market.availability_card", "availability"),
      label: "System availability",
    },
    { binding: slot("market.symbols_table", "btc"), label: "Symbols · BTC" },
    { binding: slot("market.symbols_table", "eth"), label: "Symbols · ETH" },
    { binding: slot("market.symbols_table", "sol"), label: "Symbols · SOL" },
    { binding: slot("market.regime_chip", "mark"), label: "BTC mark" },
    { binding: slot("market.freshness_gauge", "freshness"), label: "Freshness gauge" },
    { binding: slot("market.completeness_chart", "funding"), label: "BTC funding" },
  ];

  return (
    <MemberPageChrome titleKey="pages.market.title" subtitleKey="pages.market.subtitle">
      {loading ? <p className="muted">Loading live bindings...</p> : null}
      <div className="member-card-grid">
        {cards.map((card) => (
          <div key={`${card.binding.component_id}:${card.binding.slot_id}`}>
            <div className="member-card-meta" style={{ marginBottom: "0.35rem" }}>
              <MemberUxStateChip state={freshnessToUxState(card.binding.freshness)} />
            </div>
            <BoundLiveValue binding={card.binding} label={card.label} />
          </div>
        ))}
      </div>
      <p className="muted sm">
        Need Decisions? <Link to="/decisions">Open Decision Feed</Link>
      </p>
    </MemberPageChrome>
  );
}
