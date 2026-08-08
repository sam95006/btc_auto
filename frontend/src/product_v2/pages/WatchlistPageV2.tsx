import { Link } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import { loadWatchlist, removeWatch, WATCHLIST_LIMIT, type WatchItem } from "../../market/watchlistStore";
import { fetchScannerCandidates, STAGE_LABEL_ZH, type MarketCandidate } from "../../market/scannerApi";
import { formatUsd } from "../../market/freshness";
import { useLiveMarketRanking } from "../useLiveMarketRanking";
import { formatRankMove } from "../../market/liveMarketRanking";
import { SERIES_PRESETS, seriesSparkPoints } from "../../market/marketSeries";
import { MetricSpark } from "../MetricSpark";
import { TokenIcon } from "../TokenIcon";
import { useMarketSeriesBatch } from "../useMarketSeriesBatch";
import { usePublicEntitlements } from "../../member/public_entitlements_v18_2";
import { usePreviewReviewPlan } from "../../member/usePreviewReviewPlan";
import { ContextualUpgrade } from "../ContextualUpgrade";
import { FREE_WATCHLIST_SOFT_CAP, isFreePlan } from "../productCapabilities";

function fmtPct(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function agoLabel(ts?: number | null) {
  if (!ts) return "—";
  const sec = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.round(sec / 60)}m`;
  return `${Math.round(sec / 3600)}h`;
}

/** Product V2 Watchlist — true 24h/15m series sparks. */
export function WatchlistPageV2() {
  const [items, setItems] = useState<WatchItem[]>(() => loadWatchlist().items);
  const [rows, setRows] = useState<MarketCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const ranking = useLiveMarketRanking();
  const previewPlan = usePreviewReviewPlan("FREE");
  const { dto } = usePublicEntitlements(previewPlan);
  const plan = dto?.plan ?? previewPlan;
  const free = isFreePlan(plan);
  const symbols = items.filter((i) => i.assetClass === "CRYPTO").map((i) => i.symbol);
  const { seriesBySymbol } = useMarketSeriesBatch(symbols, "watchlist_24h", 90_000);

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

  const rankBySym = useMemo(() => {
    const m = new Map(ranking.rows.map((r) => [r.symbol, r]));
    return m;
  }, [ranking.rows]);

  return (
    <div data-testid="product-v2-watchlist" data-nexus-product-generation="2" data-true-market-series="1">
      <header>
        <h1 className="mp2-page-title">自選</h1>
        <p className="mp2-page-sub">本機最多 {WATCHLIST_LIMIT} · Research only · 24h/15m series</p>
      </header>

      {free && items.length >= FREE_WATCHLIST_SOFT_CAP ? (
        <ContextualUpgrade
          title="自選名額"
          detail={`FREE 建議上限 ${FREE_WATCHLIST_SOFT_CAP}；PRO 解鎖完整自選與警報聯動。`}
          required="PRO"
        />
      ) : null}

      {loading && symbols.length > 0 ? (
        <div className="mp2-skeleton-stack" aria-busy="true" aria-label="載入中">
          <div className="mp2-skeleton" style={{ height: 32 }} />
          <div className="mp2-skeleton" style={{ height: 32 }} />
        </div>
      ) : null}

      {items.length === 0 ? (
        <div className="mp2-empty">
          尚未關注任何標的。可在掃描器或探索頁加入。
          <div className="mp2-actions">
            <Link to="/scanner" className="mp2-btn mp2-btn-primary">
              開啟掃描器
            </Link>
          </div>
        </div>
      ) : (
        <div className="mp2-scanner-wrap" style={{ marginTop: 16 }}>
          <table className="mp2-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Spark</th>
                <th>Price</th>
                <th>24h</th>
                <th>NEX State</th>
                <th>Live Rank</th>
                <th>Δ</th>
                <th>Risk</th>
                <th>Updated</th>
                <th>警報</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((it) => {
                const c = rows.find((r) => r.symbol === it.symbol);
                const rr = rankBySym.get(it.symbol);
                const sparkPts = seriesSparkPoints(seriesBySymbol[it.symbol]);
                return (
                  <tr key={`${it.assetClass}:${it.symbol}`}>
                    <td>
                      {it.assetClass === "CRYPTO" ? (
                        <span className="mp2-sym-with-icon">
                          <TokenIcon symbol={it.symbol} size={18} />
                          <Link to={`/market/${it.symbol}`} className="mono">
                            {it.symbol.replace("USDT", "")}
                          </Link>
                        </span>
                      ) : (
                        <strong className="mono">{it.symbol}</strong>
                      )}
                    </td>
                    <td>
                      {sparkPts.length >= 2 ? (
                        <MetricSpark
                          points={sparkPts}
                          expectedIntervalMs={SERIES_PRESETS.watchlist_24h.expectedIntervalMs}
                          positive={(c?.change24hPct ?? 0) >= 0}
                        />
                      ) : (
                        <span className="mp2-nodata" title="NO DATA">
                          NO DATA
                        </span>
                      )}
                    </td>
                    <td className="mono">{c?.currentPrice == null ? "—" : formatUsd(c.currentPrice)}</td>
                    <td className={`mono ${(c?.change24hPct ?? 0) >= 0 ? "pos" : "neg"}`}>
                      {fmtPct(c?.change24hPct)}
                    </td>
                    <td>{c ? STAGE_LABEL_ZH[c.stage] || c.stage : "尚無候選"}</td>
                    <td className="mono">{rr ? `#${rr.rank}` : "—"}</td>
                    <td className="mono">{rr ? formatRankMove(rr) : "—"}</td>
                    <td className={`mono ${(c?.riskScore ?? 0) >= 70 ? "neg" : ""}`}>
                      {c?.riskScore == null ? "—" : Math.round(c.riskScore)}
                    </td>
                    <td className="mono muted">{agoLabel(c?.lastUpdatedAt)}</td>
                    <td>
                      <Link to="/alerts" className="mp2-btn mp2-btn-ghost" style={{ padding: "4px 8px" }}>
                        設警報
                      </Link>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="mp2-btn mp2-btn-ghost"
                        onClick={() => setItems(removeWatch(it.symbol, it.assetClass).items)}
                      >
                        移除
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
