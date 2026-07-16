import { Link } from "react-router-dom";
import { useState } from "react";
import { formatAge, formatUsd } from "../market/freshness";
import { useLiveMarketFeed } from "../market/useLiveMarketFeed";
import type { LiveSymbol } from "../market/types";
import { shortSymbol } from "../market/types";

const ORDER: LiveSymbol[] = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];

/** Market-first top header — Mainnet lastPrice + freshness (MVP-22A). */
export function MarketTopTicker() {
  const [q, setQ] = useState("");
  const feed = useLiveMarketFeed();

  return (
    <header className="market-top-ticker" role="banner">
      <div className="mtt-left">
        <Link to="/overview" className="brand-mark mtt-brand">
          NEXUS / <span>EATI</span>
        </Link>
      </div>
      <div className="mtt-center">
        {ORDER.map((sym) => {
          const p = feed.bySymbol[sym];
          const label = shortSymbol(sym);
          const ch = p?.change24hPct;
          return (
            <span key={sym} className="mtt-quote" title={p ? `${p.connectionStatus} · ${p.source}` : "Waiting"}>
              <strong>{label}</strong>
              <span className="mono mtt-price">{formatUsd(p?.lastPrice)}</span>
              <span
                className={
                  ch == null ? "muted" : ch >= 0 ? "price-up" : "price-down"
                }
              >
                {ch == null ? "—" : `${ch >= 0 ? "+" : ""}${ch.toFixed(2)}%`}
              </span>
              <span className={`mtt-fresh tone-${(p?.connectionStatus || "DISCONNECTED").toLowerCase()}`}>
                {p?.connectionStatus || "…"}
              </span>
            </span>
          );
        })}
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
        <span className="mtt-feed-chip muted" title="Feed age">
          {feed.feedStatus}
          {feed.transport !== "none" ? ` · ${formatAge(Date.now() - feed.updatedAt)}` : ""}
        </span>
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
