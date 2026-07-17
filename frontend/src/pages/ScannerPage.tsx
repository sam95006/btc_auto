import { Link } from "react-router-dom";
import { Fragment, useEffect, useMemo, useState } from "react";
import {
  STAGE_LABEL_ZH,
  plainReason,
  sideLabelZh,
  type CandidateStage,
  type MarketCandidate,
} from "../market/scannerApi";
import { useScannerBoard } from "../market/useMarketScanner";
import { formatUsd } from "../market/freshness";
import { WatchStarButton } from "../components/WatchStarButton";
import { loadViewMode, saveViewMode, type ViewMode } from "../market/viewPrefs";

type Filter =
  | "ALL"
  | "LONG"
  | "SHORT"
  | "WATCHING"
  | "AWAITING_CONFIRMATION"
  | "CONFIRMED"
  | "OVEREXTENDED"
  | "FRESH"
  | "HIGH_RISK";

type SortKey =
  | "opportunity"
  | "confirmation"
  | "risk"
  | "oi"
  | "price"
  | "turnover"
  | "liquidity"
  | "newest"
  | "rankChange";

function fmtPct(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function rankMove(c: MarketCandidate) {
  const d = c.rankDelta;
  if (d == null || d === 0) return "—";
  return d > 0 ? `↑${d}` : `↓${Math.abs(d)}`;
}

/**
 * Full market scanner board — Phase 2 product explorer (server ranking only).
 */
export function ScannerPage() {
  const { rows, status, error, loading } = useScannerBoard();
  const [filter, setFilter] = useState<Filter>("ALL");
  const [sort, setSort] = useState<SortKey>("opportunity");
  const [q, setQ] = useState("");
  const [view, setView] = useState<ViewMode>(() => loadViewMode());
  const [expanded, setExpanded] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const advanced = view === "advanced";
  const simple = view === "simple";

  useEffect(() => {
    const onView = (e: Event) => {
      const mode = (e as CustomEvent<ViewMode>).detail;
      if (mode === "simple" || mode === "advanced") setView(mode);
    };
    window.addEventListener("nexus-view-mode", onView);
    return () => window.removeEventListener("nexus-view-mode", onView);
  }, []);

  const filtered = useMemo(() => {
    let list = [...rows];
    const qq = q.trim().toUpperCase();
    if (qq) list = list.filter((r) => r.symbol.includes(qq));
    if (filter === "LONG" || filter === "SHORT") list = list.filter((r) => r.side === filter);
    else if (filter === "FRESH") list = list.filter((r) => r.freshness === "LIVE");
    else if (filter === "HIGH_RISK")
      list = list.filter((r) => r.stage === "OVEREXTENDED" || r.riskScore >= 70);
    else if (filter !== "ALL") list = list.filter((r) => r.stage === (filter as CandidateStage));

    const sorters: Record<SortKey, (a: MarketCandidate, b: MarketCandidate) => number> = {
      opportunity: (a, b) => b.opportunityScore - a.opportunityScore,
      confirmation: (a, b) => b.confirmationScore - a.confirmationScore,
      risk: (a, b) => b.riskScore - a.riskScore,
      oi: (a, b) => Math.abs(b.oiChange5mPct || 0) - Math.abs(a.oiChange5mPct || 0),
      price: (a, b) => Math.abs(b.priceChange5mPct || 0) - Math.abs(a.priceChange5mPct || 0),
      turnover: (a, b) => (b.turnoverPace || 0) - (a.turnoverPace || 0),
      liquidity: (a, b) => (b.openInterestValue || 0) - (a.openInterestValue || 0),
      newest: (a, b) => (b.firstSeenAt || 0) - (a.firstSeenAt || 0),
      rankChange: (a, b) => (b.rankDelta || 0) - (a.rankDelta || 0),
    };
    list.sort(sorters[sort]);
    return list;
  }, [rows, filter, sort, q]);

  const filters: { id: Filter; label: string }[] = [
    { id: "ALL", label: "全部" },
    { id: "LONG", label: "做多" },
    { id: "SHORT", label: "做空" },
    { id: "WATCHING", label: "觀察" },
    { id: "AWAITING_CONFIRMATION", label: "等待確認" },
    { id: "CONFIRMED", label: "已確認" },
    { id: "OVEREXTENDED", label: "過熱" },
    { id: "FRESH", label: "新鮮" },
    { id: "HIGH_RISK", label: "高風險" },
  ];

  return (
    <div className="page-stack nx-scanner-page nx-p2">
      <header className="nx-ov-header">
        <h1 className="nx-page-title">市場掃描</h1>
        <p className="nx-status-line">
          {filtered.length} / {rows.length} 結果 · {status?.freshness || "—"} · 約每{" "}
          {status?.snapshotIntervalSec ?? 20} 秒掃描 · 更新{" "}
          {status?.lastCycleAt ? new Date(status.lastCycleAt).toLocaleTimeString() : "—"}
        </p>
        <div className="nx-ov-meta">
          <Link to="/overview">← 總覽</Link>
          <Link to="/watchlist">關注</Link>
          <button
            type="button"
            className="nx-text-btn"
            onClick={() => {
              const next: ViewMode = view === "simple" ? "advanced" : "simple";
              setView(next);
              saveViewMode(next);
            }}
          >
            {advanced ? "簡易" : "進階"}
          </button>
          <button type="button" className="nx-text-btn mobile-only" onClick={() => setFiltersOpen(true)}>
            篩選
          </button>
        </div>
      </header>

      {error ? <div className="nx-banner-warn">{error}</div> : null}

      <div className={`nx-scanner-toolbar ${filtersOpen ? "open" : ""}`}>
        <div className="nx-filter-row desktop-only">
          {filters.map((f) => (
            <button
              key={f.id}
              type="button"
              className={filter === f.id ? "active" : ""}
              onClick={() => setFilter(f.id)}
            >
              {f.label}
            </button>
          ))}
        </div>
        {filtersOpen ? (
          <div className="nx-filter-sheet mobile-only">
            <div className="nx-filter-row">
              {filters.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  className={filter === f.id ? "active" : ""}
                  onClick={() => {
                    setFilter(f.id);
                    setFiltersOpen(false);
                  }}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <button type="button" className="nx-text-btn" onClick={() => setFiltersOpen(false)}>
              關閉
            </button>
          </div>
        ) : null}
        <div className="nx-sort-row">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="搜尋 symbol…"
            className="nx-search"
          />
          <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)} aria-label="排序">
            <option value="opportunity">機會分數</option>
            <option value="confirmation">確認程度</option>
            <option value="risk">風險程度</option>
            <option value="oi">持倉變動</option>
            <option value="price">價格動能</option>
            <option value="turnover">交易活躍</option>
            <option value="liquidity">流動性</option>
            <option value="newest">最新</option>
            <option value="rankChange">排名變化</option>
          </select>
        </div>
      </div>

      {/* Desktop table */}
      <div className="nx-scanner-table-wrap desktop-only">
        <table className="nx-scanner-table sticky-head">
          <thead>
            <tr>
              <th>#</th>
              <th>Symbol</th>
              <th>方向</th>
              <th>階段</th>
              <th className={sort === "opportunity" ? "sorted" : ""}>機會</th>
              <th>確認</th>
              <th>風險</th>
              <th>價 5m</th>
              <th>持倉 5m</th>
              <th>活躍</th>
              <th>排名</th>
              <th>新鮮度</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {loading && filtered.length === 0 ? (
              <tr>
                <td colSpan={13} className="muted">
                  資料累積中…
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={13} className="muted">
                  篩選後無結果（不會用假候選填空）
                </td>
              </tr>
            ) : (
              filtered.map((r) => (
                <Fragment key={r.id}>
                  <tr
                    className="nx-scan-row"
                    tabIndex={0}
                    onClick={() => setExpanded(expanded === r.id ? null : r.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") setExpanded(expanded === r.id ? null : r.id);
                    }}
                  >
                    <td className="mono">{r.rank ?? "—"}</td>
                    <td>
                      <Link to={`/market/${r.symbol}`} className="mono" onClick={(e) => e.stopPropagation()}>
                        {r.symbol.replace("USDT", "")}
                      </Link>
                    </td>
                    <td>
                      <span className={`nx-side-mark side-${r.side.toLowerCase()}`}>
                        {r.side === "LONG" ? "▲" : r.side === "SHORT" ? "▼" : "·"} {sideLabelZh(r.side)}
                      </span>
                    </td>
                    <td>{STAGE_LABEL_ZH[r.stage]}</td>
                    <td className="mono">{Math.round(r.opportunityScore)}</td>
                    <td className="mono">{Math.round(r.confirmationScore)}</td>
                    <td className="mono">{Math.round(r.riskScore)}</td>
                    <td className="mono">{fmtPct(r.priceChange5mPct)}</td>
                    <td className="mono">{fmtPct(r.oiChange5mPct)}</td>
                    <td className="mono">{r.turnoverPace != null ? r.turnoverPace.toFixed(2) : "—"}</td>
                    <td className="mono">{rankMove(r)}</td>
                    <td>{r.freshness}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <WatchStarButton symbol={r.symbol} />
                    </td>
                  </tr>
                  {expanded === r.id ? (
                    <tr className="nx-row-expand">
                      <td colSpan={13}>
                        <p>{plainReason(r.reasons?.[0] || "—", simple)}</p>
                        {r.conflicts?.[0] ? (
                          <p className="muted">風險：{plainReason(r.conflicts[0], simple)}</p>
                        ) : null}
                        {advanced ? (
                          <dl className="nx-kv mono sm">
                            <div>
                              <dt>Funding</dt>
                              <dd>
                                {r.fundingRate != null ? `${(r.fundingRate * 100).toFixed(4)}%` : "—"}
                              </dd>
                            </div>
                            <div>
                              <dt>Spread</dt>
                              <dd>{r.spreadBps != null ? r.spreadBps.toFixed(1) : "—"}</dd>
                            </div>
                            <div>
                              <dt>OI Value</dt>
                              <dd>{r.openInterestValue ?? "—"}</dd>
                            </div>
                            <div>
                              <dt>Price</dt>
                              <dd>{formatUsd(r.currentPrice)}</dd>
                            </div>
                          </dl>
                        ) : null}
                        <Link to={`/market/${r.symbol}`}>開啟詳情 →</Link>
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Mobile cards */}
      <div className="nx-scanner-cards mobile-only">
        {loading && filtered.length === 0 ? (
          <p className="muted">資料累積中…</p>
        ) : filtered.length === 0 ? (
          <p className="muted">篩選後無結果</p>
        ) : (
          filtered.map((r) => (
            <article key={r.id} className="nx-scan-card">
              <div className="nx-cand-top">
                <span className="nx-cand-rank">#{r.rank ?? "—"}</span>
                <Link to={`/market/${r.symbol}`} className="mono nx-cand-sym">
                  {r.symbol.replace("USDT", "")}
                </Link>
                <WatchStarButton symbol={r.symbol} />
              </div>
              <p className="nx-stage-line">
                <span className={`nx-side-mark side-${r.side.toLowerCase()}`}>
                  {r.side === "LONG" ? "▲" : "▼"}
                </span>{" "}
                {STAGE_LABEL_ZH[r.stage]}
              </p>
              <div className="nx-opp-primary inline">
                <span className="nx-score-label">機會</span>
                <span className="nx-score-val">{Math.round(r.opportunityScore)}</span>
              </div>
              <p className="nx-cand-reason">{plainReason(r.reasons?.[0] || "—", simple)}</p>
              <div className="nx-cand-moves">
                <span>確認 {Math.round(r.confirmationScore)}</span>
                <span className={r.riskScore >= 70 ? "risk" : ""}>風險 {Math.round(r.riskScore)}</span>
                <span>價 {fmtPct(r.priceChange5mPct)}</span>
                <span>持倉 {fmtPct(r.oiChange5mPct)}</span>
                <span>{rankMove(r)}</span>
              </div>
              <div className="muted sm">{r.freshness}</div>
            </article>
          ))
        )}
      </div>
    </div>
  );
}
