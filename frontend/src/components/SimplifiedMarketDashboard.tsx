import { LONG_WATCHLIST, SHORT_WATCHLIST } from "../demo/marketDashboard";
import { CompactSafetyStrip } from "./CompactSafetyStrip";
import { DecisionAlertsPanel } from "./DecisionAlertsPanel";
import { MarketReadinessGauge } from "./MarketReadinessGauge";
import { RecommendationBoard } from "./RecommendationBoard";

/**
 * DataHunterX-style market home — boards first, minimal prose (MVP-22).
 */
export function SimplifiedMarketDashboard() {
  return (
    <div className="simplified-market-dashboard" id="market-dashboard">
      <CompactSafetyStrip />
      <p className="sr-only">
        READ ONLY. NOT INVESTMENT ADVICE. Demo market dashboard. No live trading.
      </p>

      <p className="dash-focus-line">
        Focus: <strong className="mono">ETH</strong> · status WAIT · next View Gate
      </p>

      <div className="dash-main-grid">
        <div className="dash-boards">
          <RecommendationBoard title="Long Watchlist" rows={LONG_WATCHLIST} focusSymbol="ETH" />
          <RecommendationBoard
            title="Short Watchlist"
            rows={SHORT_WATCHLIST}
            emptyNote="No active short candidate · Monitoring only · Read-only"
          />
        </div>
        <MarketReadinessGauge />
      </div>

      <DecisionAlertsPanel />
    </div>
  );
}
