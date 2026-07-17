import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { loadWatchlist, removeWatch, WATCHLIST_LIMIT } from "../market/watchlistStore";
import { fetchScannerCandidates, STAGE_LABEL_ZH, sideLabelZh, type MarketCandidate } from "../market/scannerApi";
import { formatUsd } from "../market/freshness";

/**
 * Local watchlist — no account / cloud sync.
 */
export function WatchlistPage() {
  const [symbols, setSymbols] = useState(() => loadWatchlist().symbols);
  const [rows, setRows] = useState<MarketCandidate[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const body = await fetchScannerCandidates(undefined, 40);
        if (!alive) return;
        const map = new Map((body.candidates || []).map((c) => [c.symbol, c]));
        setRows(symbols.map((s) => map.get(s)).filter(Boolean) as MarketCandidate[]);
      } catch {
        if (alive) setRows([]);
      } finally {
        if (alive) setLoading(false);
      }
    };
    void load();
    const id = window.setInterval(() => void load(), 12000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [symbols]);

  return (
    <div className="page-stack nx-watchlist-page">
      <header className="nx-ov-header">
        <h1 className="nx-page-title">關注清單</h1>
        <p className="nx-status-line">
          本機儲存 · 最多 {WATCHLIST_LIMIT} · 不需帳戶 · Research only
        </p>
        <Link to="/scanner">← 掃描器</Link>
      </header>
      {loading && symbols.length > 0 ? <p className="muted">載入中…</p> : null}
      {symbols.length === 0 ? (
        <p className="muted">尚未關注任何標的。可在候選卡或詳情頁點星號加入。</p>
      ) : (
        <ul className="nx-watch-list">
          {symbols.map((sym) => {
            const c = rows.find((r) => r.symbol === sym);
            return (
              <li key={sym} className="nx-watch-row">
                <Link to={`/market/${sym}`} className="nx-watch-main">
                  <strong className="mono">{sym.replace("USDT", "")}</strong>
                  {c ? (
                    <>
                      <span>{sideLabelZh(c.side)}</span>
                      <span>{STAGE_LABEL_ZH[c.stage]}</span>
                      <span className="mono">{formatUsd(c.currentPrice)}</span>
                      <span>機會 {Math.round(c.opportunityScore)}</span>
                      <span className="muted">{c.freshness}</span>
                    </>
                  ) : (
                    <span className="muted">目前不在掃描池或尚無候選</span>
                  )}
                </Link>
                <button
                  type="button"
                  className="nx-text-btn"
                  onClick={() => setSymbols(removeWatch(sym).symbols)}
                >
                  移除
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
