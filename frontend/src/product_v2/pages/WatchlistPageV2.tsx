import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { loadWatchlist, removeWatch, WATCHLIST_LIMIT, type WatchItem } from "../../market/watchlistStore";
import { fetchScannerCandidates, STAGE_LABEL_ZH, sideLabelZh, type MarketCandidate } from "../../market/scannerApi";
import { formatUsd } from "../../market/freshness";
import { plainReason } from "../../market/scannerApi";

/**
 * Product V2 Watchlist — personal workspace (state / change / risk / next condition / alert).
 */
export function WatchlistPageV2() {
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
    <div data-testid="product-v2-watchlist" data-nexus-product-generation="2">
      <header>
        <h1 className="mp2-page-title">自選</h1>
        <p className="mp2-page-sub">
          個人工作區 · 本機最多 {WATCHLIST_LIMIT} · Research only
        </p>
      </header>

      {loading && symbols.length > 0 ? <p className="muted">載入中…</p> : null}

      {items.length === 0 ? (
        <div className="mp2-empty">
          尚未關注任何標的。可在掃描器或機會頁加入。
          <div className="mp2-actions">
            <Link to="/scanner" className="mp2-btn mp2-btn-primary">
              開啟掃描器
            </Link>
          </div>
        </div>
      ) : (
        <div style={{ marginTop: 16 }}>
          <div
            className="mp2-watch-row muted"
            style={{ fontSize: "0.6875rem", textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 650 }}
          >
            <span>標的／狀態</span>
            <span>變化</span>
            <span>風險</span>
            <span>下一步條件</span>
            <span>警報</span>
            <span />
          </div>
          {items.map((it) => {
            const c = rows.find((r) => r.symbol === it.symbol);
            const change =
              c?.priceChange5mPct == null
                ? "—"
                : `${c.priceChange5mPct > 0 ? "+" : ""}${c.priceChange5mPct.toFixed(2)}%`;
            const next =
              c == null
                ? "等待掃描池納入"
                : plainReason(c.reasons?.[0] || c.invalidationContext || "持續觀察結構", true);
            return (
              <div key={`${it.assetClass}:${it.symbol}`} className="mp2-watch-row">
                <div>
                  {it.assetClass === "CRYPTO" ? (
                    <Link to={`/market/${it.symbol}`} className="mono" style={{ fontWeight: 650, color: "var(--mp2-ink)" }}>
                      {it.symbol.replace("USDT", "")}
                    </Link>
                  ) : (
                    <strong className="mono">{it.symbol}</strong>
                  )}
                  <div className="muted" style={{ fontSize: "0.75rem" }}>
                    {it.assetClass}
                    {c ? ` · ${sideLabelZh(c.side)} · ${STAGE_LABEL_ZH[c.stage]}` : " · 尚無候選"}
                    {c ? ` · ${formatUsd(c.currentPrice)}` : ""}
                  </div>
                </div>
                <span className={`mono ${(c?.priceChange5mPct ?? 0) >= 0 ? "pos" : "neg"}`}>{change}</span>
                <span className={`mono ${(c?.riskScore ?? 0) >= 70 ? "neg" : ""}`}>
                  {c?.riskScore == null ? "—" : Math.round(c.riskScore)}
                </span>
                <span style={{ fontSize: "0.8125rem" }}>{next}</span>
                <span>
                  <Link to="/alerts" className="mp2-btn mp2-btn-ghost" style={{ padding: "4px 8px" }}>
                    設警報
                  </Link>
                </span>
                <button
                  type="button"
                  className="mp2-btn mp2-btn-ghost"
                  onClick={() => setItems(removeWatch(it.symbol, it.assetClass).items)}
                >
                  移除
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
