import { Link } from "react-router-dom";
import { useState } from "react";
import { NEXUS_UI_BUILD_INFO } from "../demo/buildInfo";
import { TICKER_QUOTES } from "../demo/marketDashboard";

/** Compact market top header — prices + HOLD (MVP-22). */
export function MarketTopTicker() {
  const [q, setQ] = useState("");
  return (
    <header className="market-top-ticker" role="banner">
      <div className="mtt-left">
        <Link to="/overview" className="brand-mark mtt-brand">
          NEXUS / <span>EATI</span>
        </Link>
      </div>
      <div className="mtt-center">
        {TICKER_QUOTES.map((t) => (
          <span key={t.symbol} className="mtt-quote">
            <strong>{t.symbol}</strong>
            <span className="mono">{t.price}</span>
            <span className={t.changePct >= 0 ? "price-up" : "price-down"}>
              {t.changePct >= 0 ? "+" : ""}
              {t.changePct.toFixed(2)}%
            </span>
          </span>
        ))}
        <span className="status-chip tone-hold compact">
          Backend: <strong>HOLD</strong>
        </span>
        <span className="status-chip mode compact">
          Mode: <strong>READ ONLY</strong>
        </span>
        <span className="status-chip tone-blocked compact mtt-419" title="Stage 4.19 blocked">
          4.19 BLOCKED
        </span>
      </div>
      <div className="mtt-right">
        <label className="mtt-search">
          <span className="sr-only">Search</span>
          <input
            type="search"
            placeholder="Search…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Search (local UI only)"
          />
        </label>
        <Link className="mtt-icon" to="/overview#decision-alerts" title="Alerts">
          Alerts
        </Link>
        <Link className="mtt-icon" to="/assistant" title="AI Assistant">
          AI
        </Link>
        <span className="mtt-icon muted" title={`UI ${NEXUS_UI_BUILD_INFO.displayLabel}`}>
          UI
        </span>
      </div>
    </header>
  );
}
