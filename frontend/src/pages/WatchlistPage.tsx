import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { loadWatchlist, removeWatch, WATCHLIST_LIMIT, type WatchItem } from "../market/watchlistStore";
import { fetchScannerCandidates, STAGE_LABEL_ZH, sideLabelZh, type MarketCandidate } from "../market/scannerApi";
import { formatUsd } from "../market/freshness";

/**
 * Local watchlist — no account / cloud sync. Phase 3 schema v2 with assetClass.
 */
export function WatchlistPage() {
  const [items, setItems] = useState<WatchItem[]>(() => loadWatchlist().items);
  const [rows, setRows] = useState<MarketCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const symbols = items.filter((i) => i.assetClass === "CRYPTO").map((i) => i.symbol);

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
  }, [symbols.join(",")]);

  return (
    <div className="page-stack nx-watchlist-page">
      <header className="nx-ov-header">
        <h1 className="nx-page-title">關注清單</h1>
        <p className="nx-status-line">
          本機儲存 · 最多 {WATCHLIST_LIMIT} · 支援 CRYPTO／美股類別骨架 · 不需帳戶 · Research only
        </p>
        <Link to="/scanner">← 掃描器</Link>
      </header>
      {loading && symbols.length > 0 ? <p className="muted">載入中…</p> : null}
      {items.length === 0 ? (
        <p className="muted">尚未關注任何標的。可在候選卡或詳情頁點星號加入。</p>
      ) : (
        <ul className="nx-watch-list">
          {items.map((it) => {
            const c = rows.find((r) => r.symbol === it.symbol);
            return (
              <li key={`${it.assetClass}:${it.symbol}`} className="nx-watch-row">
                {it.assetClass === "CRYPTO" ? (
                  <Link to={`/market/${it.symbol}`} className="nx-watch-main">
                    <strong className="mono">{it.symbol.replace("USDT", "")}</strong>
                    <span className="muted">CRYPTO</span>
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
                ) : (
                  <div className="nx-watch-main">
                    <strong className="mono">{it.symbol}</strong>
                    <span className="muted">{it.assetClass}</span>
                    <span className="muted">資料提供者尚未連接</span>
                  </div>
                )}
                <button
                  type="button"
                  className="nx-text-btn"
                  onClick={() => setItems(removeWatch(it.symbol, it.assetClass).items)}
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
