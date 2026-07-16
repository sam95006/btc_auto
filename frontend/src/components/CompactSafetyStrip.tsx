import { useLiveMarketFeed } from "../market/useLiveMarketFeed";
import { formatAge } from "../market/freshness";

/** Single status line: market feed + HOLD gate (MVP-22A). */
export function CompactSafetyStrip() {
  const feed = useLiveMarketFeed();
  const ageLabel =
    feed.transport === "none" ? "—" : formatAge(Math.max(0, Date.now() - feed.updatedAt));
  const tone = feed.feedStatus.toLowerCase();

  return (
    <div className="compact-safety-strip" role="status">
      <span className={`css-status-line feed-${tone}`}>
        ● {feed.feedStatus} · BYBIT MAINNET LINEAR · LAST PRICE · updated {ageLabel}
        {feed.transport === "rest" ? " · REST FALLBACK" : ""}
      </span>
      <span className="css-status-line hold-bits">
        Backend HOLD · ETH Gate Waiting · Stage 4.19 Blocked · Read-only
      </span>
      <span className="css-safe-badges" aria-label="Safety">
        <span className="css-pill pass">Safe</span>
        <span className="css-pill">No live trading</span>
      </span>
    </div>
  );
}
