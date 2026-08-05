import { Link } from "react-router-dom";
import { MemberPageChrome } from "../../member/MemberPageChrome";
import { BoundLiveValue, useLiveBindings } from "../../public_v2_live_binding";

export function MemberMarketOverviewPage() {
  const { slot, loading } = useLiveBindings();

  return (
    <MemberPageChrome
      title="Market Overview"
      subtitle="Public live bindings with lineage · not a trading blotter"
    >
      {loading ? <p className="muted">Loading live bindings...</p> : null}
      <div className="member-card-grid">
        <BoundLiveValue binding={slot("market.overview_btc_card", "price")} label="BTC last" />
        <BoundLiveValue binding={slot("market.overview_eth_card", "price")} label="ETH last" />
        <BoundLiveValue binding={slot("market.freshness_card", "freshness")} label="Feed freshness" />
        <BoundLiveValue
          binding={slot("market.availability_card", "availability")}
          label="System availability"
        />
        <BoundLiveValue binding={slot("market.symbols_table", "btc")} label="Symbols · BTC" />
        <BoundLiveValue binding={slot("market.symbols_table", "eth")} label="Symbols · ETH" />
        <BoundLiveValue binding={slot("market.symbols_table", "sol")} label="Symbols · SOL" />
        <BoundLiveValue binding={slot("market.regime_chip", "mark")} label="BTC mark" />
        <BoundLiveValue binding={slot("market.freshness_gauge", "freshness")} label="Freshness gauge" />
        <BoundLiveValue
          binding={slot("market.completeness_chart", "funding")}
          label="BTC funding"
        />
      </div>
      <p className="muted sm">
        Need Decisions? <Link to="/decisions">Open Decision Feed</Link>
      </p>
    </MemberPageChrome>
  );
}
