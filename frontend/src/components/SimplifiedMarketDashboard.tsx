import { Link } from "react-router-dom";
import { LONG_WATCHLIST, SHORT_WATCHLIST } from "../demo/marketDashboard";
import { CompactSafetyStrip } from "./CompactSafetyStrip";
import { DecisionAlertsPanel } from "./DecisionAlertsPanel";
import { MarketReadinessGauge } from "./MarketReadinessGauge";
import { RecommendationBoard } from "./RecommendationBoard";

/**
 * DataHunterX-style market home — visual boards, minimal prose (MVP-22).
 * Gate/Evidence details stay on their pages.
 */
export function SimplifiedMarketDashboard() {
  return (
    <div className="simplified-market-dashboard" id="market-dashboard">
      <CompactSafetyStrip />
      <p className="dash-one-liner muted">
        Read-only research mode. No regression should run now.{" "}
        <span className="sr-only">NOT INVESTMENT ADVICE</span>
      </p>

      <div className="dash-main-grid">
        <div className="dash-boards">
          <RecommendationBoard title="Long Watchlist" rows={LONG_WATCHLIST} />
          <RecommendationBoard
            title="Short Watchlist"
            rows={SHORT_WATCHLIST}
            emptyNote="No active short candidate · Monitoring only · Read-only"
          />
        </div>
        <MarketReadinessGauge />
      </div>

      <DecisionAlertsPanel />

      <div className="dash-secondary-links muted">
        <Link className="deep-link" to="/evidence#start-here">
          Evidence
        </Link>
        <span>·</span>
        <Link className="deep-link" to="/risk-evidence#why-safe">
          Risk
        </Link>
        <span>·</span>
        <Link className="deep-link" to="/provider-shadow#provider-explain">
          Provider
        </Link>
        <span>·</span>
        <Link className="deep-link" to="/overview#gate-checklist-detail">
          Gate details
        </Link>
      </div>
    </div>
  );
}
