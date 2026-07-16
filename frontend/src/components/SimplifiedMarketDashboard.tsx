import { LONG_WATCHLIST, SHORT_WATCHLIST, SIGNAL_REFERENCES } from "../demo/marketDashboard";
import { formatUsd } from "../market/freshness";
import { useLivePrice } from "../market/useLiveMarketFeed";
import { CompactSafetyStrip } from "./CompactSafetyStrip";
import { DecisionAlertsPanel } from "./DecisionAlertsPanel";
import { MarketContextPanel } from "./MarketContextPanel";
import { MarketReadinessGauge } from "./MarketReadinessGauge";
import { RecommendationBoard } from "./RecommendationBoard";

function FocusEthBlock() {
  const live = useLivePrice("ETH");
  const signal = SIGNAL_REFERENCES.ETH;
  return (
    <div className="dash-focus-block">
      <p className="dash-focus-line">
        Focus: <strong className="mono">ETH</strong> · status WAIT · next View Gate
      </p>
      <div className="focus-price-grid">
        <div>
          <div className="muted focus-k">Current Market Price</div>
          <div className="mono focus-v">{formatUsd(live?.lastPrice)}</div>
        </div>
        <div>
          <div className="muted focus-k">Signal Reference Price</div>
          <div className="mono focus-v">{formatUsd(signal.referencePrice)}</div>
        </div>
        <div>
          <div className="muted focus-k">Signal Generated At</div>
          <div className="mono focus-v">{new Date(signal.analysisTimestamp).toISOString()}</div>
        </div>
        <div>
          <div className="muted focus-k">Market Updated At</div>
          <div className="mono focus-v">
            {live ? new Date(live.receivedAt).toISOString() : "—"}
          </div>
        </div>
      </div>
      <details className="focus-mark-details">
        <summary className="muted">Mark / Index (secondary)</summary>
        <div className="mono muted">
          Mark {formatUsd(live?.markPrice)} · Index {formatUsd(live?.indexPrice)} ·{" "}
          {live?.connectionStatus || "DISCONNECTED"}
        </div>
      </details>
      <MarketContextPanel symbol="ETH" recommendation={signal.recommendation || "WAIT"} />
    </div>
  );
}

/**
 * Market home — live lastPrice + derivatives context (MVP-22B).
 */
export function SimplifiedMarketDashboard() {
  return (
    <div className="simplified-market-dashboard" id="market-dashboard">
      <CompactSafetyStrip />
      <p className="sr-only">
        READ ONLY. NOT INVESTMENT ADVICE. Live Mainnet public market data for display only. No live
        trading.
      </p>

      <FocusEthBlock />

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
