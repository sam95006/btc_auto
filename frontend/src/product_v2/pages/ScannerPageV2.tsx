import { Link } from "react-router-dom";
import { useMemo, useState } from "react";
import {
  STAGE_LABEL_ZH,
  plainReason,
  type MarketCandidate,
} from "../../market/scannerApi";
import { useScannerBoard } from "../../market/useMarketScanner";
import { formatUsd } from "../../market/freshness";
import { WatchStarButton } from "../../components/WatchStarButton";
import { memberDataTrustLabel } from "../../market/marketMetricFunnel";
import { useLiveMarketRanking } from "../useLiveMarketRanking";
import { formatRankMove, type LiveRankingRow } from "../../market/liveMarketRanking";

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

/**
 * Product V2 Scanner — market-data-first columns + right detail drawer.
 */
export function ScannerPageV2() {
  const { rows, status, error, loading } = useScannerBoard();
  const ranking = useLiveMarketRanking();
  const [q, setQ] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(true);

  const rankBySym = useMemo(() => {
    const m = new Map<string, LiveRankingRow>();
    for (const r of ranking.rows) m.set(r.symbol, r);
    return m;
  }, [ranking.rows]);

  const filtered = useMemo(() => {
    let list = [...rows];
    const qq = q.trim().toUpperCase();
    if (qq) list = list.filter((r) => r.symbol.includes(qq));
    list.sort((a, b) => {
      const ra = rankBySym.get(a.symbol)?.rank ?? 9999;
      const rb = rankBySym.get(b.symbol)?.rank ?? 9999;
      if (ra !== rb) return ra - rb;
      return (b.opportunityScore ?? -1) - (a.opportunityScore ?? -1);
    });
    return list;
  }, [rows, q, rankBySym]);

  const selected = filtered.find((r) => r.id === selectedId) ?? null;
  const selectedRank = selected ? rankBySym.get(selected.symbol) : undefined;

  return (
    <div data-testid="product-v2-scanner" data-nexus-product-generation="2">
      <header>
        <h1 className="mp2-page-title">掃描器</h1>
        <p className="mp2-page-sub">
          {filtered.length} / {rows.length} · {status?.freshness || "更新未知"} · 約每{" "}
          {status?.snapshotIntervalSec ?? 20} 秒
        </p>
      </header>

      {error ? <div className="mp2-banner">{error}</div> : null}

      <div className="mp2-scanner-toolbar">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜尋標的…" aria-label="搜尋標的" />
        <button type="button" className="mp2-btn" onClick={() => setDrawerOpen((v) => !v)}>
          {drawerOpen ? "收合詳情" : "展開詳情"}
        </button>
      </div>

      <div className={`mp2-scanner-layout${drawerOpen ? "" : " no-drawer"}`}>
        <div className="mp2-scanner-wrap">
          <table className="mp2-table" data-testid="scanner-table">
            <thead>
              <tr>
                <th>☆</th>
                <th>Symbol</th>
                <th>Price</th>
                <th>24h</th>
                <th>Volume</th>
                <th>NEX State</th>
                <th>Rank</th>
                <th>Risk</th>
                <th>Funding</th>
                <th>OI</th>
                <th>Activity</th>
                <th>Data</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {loading && !filtered.length ? (
                <tr>
                  <td colSpan={13} className="muted">
                    載入中…
                  </td>
                </tr>
              ) : null}
              {!loading && !filtered.length ? (
                <tr>
                  <td colSpan={13} className="muted">
                    無符合條件的列
                  </td>
                </tr>
              ) : null}
              {filtered.map((c) => {
                const rr = rankBySym.get(c.symbol);
                const vol = (c as MarketCandidate & { volume24h?: number }).volume24h;
                return (
                  <tr
                    key={c.id}
                    className={selected?.id === c.id ? "is-selected" : undefined}
                    onClick={() => {
                      setSelectedId(c.id);
                      setDrawerOpen(true);
                    }}
                  >
                    <td onClick={(e) => e.stopPropagation()}>
                      <WatchStarButton symbol={c.symbol} />
                    </td>
                    <td>
                      <Link to={`/market/${c.symbol}`} className="mono" onClick={(e) => e.stopPropagation()}>
                        {c.symbol.replace("USDT", "")}
                      </Link>
                    </td>
                    <td className="mono">{c.currentPrice == null ? "—" : formatUsd(c.currentPrice)}</td>
                    <td className={`mono ${(c.change24hPct ?? 0) >= 0 ? "pos" : "neg"}`}>
                      {fmtPct(c.change24hPct)}
                    </td>
                    <td className="mono">{vol == null ? "—" : Number(vol).toLocaleString()}</td>
                    <td>{STAGE_LABEL_ZH[c.stage] || c.stage}</td>
                    <td className="mono">{rr ? formatRankMove(rr) : c.rank != null ? `#${c.rank}` : "—"}</td>
                    <td className={`mono ${(c.riskScore ?? 0) >= 70 ? "neg" : ""}`}>
                      {c.riskScore == null ? "—" : Math.round(c.riskScore)}
                    </td>
                    <td className="mono">
                      {c.fundingRate == null ? "—" : `${(c.fundingRate * 100).toFixed(4)}%`}
                    </td>
                    <td className="mono">{fmtPct(c.oiChange5mPct)}</td>
                    <td className="mono">{rr?.activity_state || "—"}</td>
                    <td>{memberDataTrustLabel({ scannerFreshness: c.freshness }).label_zh}</td>
                    <td className="mono muted">{agoLabel(c.lastUpdatedAt)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {drawerOpen && selected ? (
          <aside className="mp2-scanner-drawer" data-testid="scanner-detail-drawer" aria-label="掃描詳情">
            <p className="mp2-kicker">快速檢視</p>
            <h2 className="mono" style={{ margin: "0 0 8px", fontSize: "1.15rem" }}>
              {selected.symbol.replace("USDT", "")}
            </h2>
            <dl className="mp2-term-dl">
              <div>
                <dt>Price</dt>
                <dd className="mono">
                  {selected.currentPrice == null ? "—" : formatUsd(selected.currentPrice)}
                </dd>
              </div>
              <div>
                <dt>24h</dt>
                <dd className="mono">{fmtPct(selected.change24hPct)}</dd>
              </div>
              <div>
                <dt>Live Radar</dt>
                <dd className="mono">{selectedRank ? formatRankMove(selectedRank) : "—"}</dd>
              </div>
              <div>
                <dt>NEX State</dt>
                <dd>{STAGE_LABEL_ZH[selected.stage] || selected.stage}</dd>
              </div>
              <div>
                <dt>Activity</dt>
                <dd>{selectedRank?.activity_state || "—"}</dd>
              </div>
              <div>
                <dt>Funding</dt>
                <dd className="mono">
                  {selected.fundingRate == null ? "—" : `${(selected.fundingRate * 100).toFixed(4)}%`}
                </dd>
              </div>
              <div>
                <dt>OI</dt>
                <dd className="mono">{fmtPct(selected.oiChange5mPct)}</dd>
              </div>
              <div>
                <dt>Risk</dt>
                <dd className="mono">{selected.riskScore == null ? "—" : Math.round(selected.riskScore)}</dd>
              </div>
              <div>
                <dt>Data Trust</dt>
                <dd>{memberDataTrustLabel({ scannerFreshness: selected.freshness }).label_zh}</dd>
              </div>
            </dl>
            <p className="mp2-kicker">主要原因</p>
            <p>{plainReason(selected.reasons?.[0] || "—", true)}</p>
            <div className="mp2-actions">
              <Link to={`/market/${selected.symbol}`} className="mp2-btn mp2-btn-primary">
                完整分析
              </Link>
              <Link to="/alerts" className="mp2-btn">
                設警報
              </Link>
              <WatchStarButton symbol={selected.symbol} />
            </div>
          </aside>
        ) : null}
      </div>
    </div>
  );
}
