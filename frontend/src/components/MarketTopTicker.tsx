import { Link } from "react-router-dom";
import { useState } from "react";
import { TICKER_QUOTES } from "../demo/marketDashboard";

/** Market-first top header — prices dominate, status is compact (MVP-22). */
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
            <span className="mono mtt-price">{t.price}</span>
            <span className={t.changePct >= 0 ? "price-up" : "price-down"}>
              {t.changePct >= 0 ? "+" : ""}
              {t.changePct.toFixed(1)}%
            </span>
          </span>
        ))}
        <span className="mtt-status-plain">
          Backend <strong>HOLD</strong>
        </span>
        <span className="mtt-status-plain">
          <strong>READ ONLY</strong>
        </span>
        <span className="mtt-badge-419" title="Stage 4.19 blocked">
          4.19
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
        <Link className="mtt-icon" to="/overview#decision-alerts" title="Alerts" aria-label="Alerts">
          ⌂
        </Link>
        <button
          type="button"
          className="mtt-icon"
          title="AI Assistant"
          aria-label="Open AI Assistant"
          onClick={() => {
            document.querySelector<HTMLButtonElement>(".floating-ai-fab")?.click();
          }}
        >
          AI
        </button>
        <span className="mtt-icon muted" title="Theme (static)">
          ◐
        </span>
      </div>
    </header>
  );
}
