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
import { loadViewMode, type ViewMode } from "../market/viewPrefs";
import {
  resolveColumnPreset,
  visibleColumns,
  viewModeToPreset,
  type ColumnPreset,
} from "../wave4/columnPresets";
import { UiDensityToggle } from "../member/UiDensityToggle";
import {
  densityToViewMode,
  loadUiDensity,
  saveUiDensity,
  type UiDensity,
  viewModeToDensity,
} from "../member/uiDensityPrefs";

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

type ScannerPageProps = {
  columnPreset?: ColumnPreset;
  hideHeader?: boolean;
};

/**
 * Full-market professional scanner — search + filters; SIMPLE vs EXPERT columns.
 */
export function ScannerPage({ columnPreset, hideHeader = false }: ScannerPageProps = {}) {
  const { rows, status, error, loading } = useScannerBoard();
  const [filter, setFilter] = useState<Filter>("ALL");
  const [sort, setSort] = useState<SortKey>("opportunity");
  const [q, setQ] = useState("");
  const [density, setDensity] = useState<UiDensity>(() => loadUiDensity());
  const [view, setView] = useState<ViewMode>(() => densityToViewMode(loadUiDensity()) || loadViewMode());
  const [expanded, setExpanded] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const advanced = view === "advanced" || density === "EXPERT";
  const simple = !advanced;
  const preset = columnPreset ?? (advanced ? viewModeToPreset("advanced") : resolveColumnPreset());
  const cols = visibleColumns(preset);
  const showCol = (id: string) => cols.some((c) => c.id === id);

  const onDensity = (d: UiDensity) => {
    setDensity(d);
    saveUiDensity(d);
    setView(densityToViewMode(d));
  };

  useEffect(() => {
    const onView = (e: Event) => {
      const mode = (e as CustomEvent<ViewMode>).detail;
      if (mode === "simple" || mode === "advanced") {
        setView(mode);
        setDensity(viewModeToDensity(mode));
      }
    };
    const onDensityEvt = (e: Event) => {
      const d = (e as CustomEvent<UiDensity>).detail;
      if (d === "SIMPLE" || d === "EXPERT") {
        setDensity(d);
        setView(densityToViewMode(d));
      }
    };
    window.addEventListener("nexus-view-mode", onView);
    window.addEventListener("nexus-ui-density", onDensityEvt);
    return () => {
      window.removeEventListener("nexus-view-mode", onView);
      window.removeEventListener("nexus-ui-density", onDensityEvt);
    };
  }, []);

  const filtered = useMemo(() => {
    let list = [...rows];
    const qq = q.trim().toUpperCase();
    if (qq) list = list.filter((r) => r.symbol.includes(qq));
    if (filter === "LONG" || filter === "SHORT") list = list.filter((r) => r.side === filter);
    else if (filter === "FRESH") list = list.filter((r) => r.freshness === "LIVE");
    else if (filter === "HIGH_RISK")
      list = list.filter((r) => r.stage === "OVEREXTENDED" || (r.riskScore != null && r.riskScore >= 70));
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

  const primaryFilters: { id: Filter; label: string }[] = [
    { id: "ALL", label: "全部" },
    { id: "LONG", label: "做多" },
    { id: "SHORT", label: "做空" },
    { id: "CONFIRMED", label: "已確認" },
    { id: "HIGH_RISK", label: "高風險" },
  ];

  const stageFilters: { id: Filter; label: string }[] = [
    { id: "WATCHING", label: "觀察" },
    { id: "AWAITING_CONFIRMATION", label: "等待確認" },
    { id: "OVEREXTENDED", label: "過熱" },
    { id: "FRESH", label: "新鮮" },
  ];

  return (
    <div className="page-stack nx-scanner-page nx-scanner-v1827 nx-p2">
      {!hideHeader ? (
        <header className="nx-ov-global-header">
          <div>
            <h1 className="nx-page-title">掃描器</h1>
            <p className="nx-status-line muted" style={{ margin: "4px 0 0" }}>
              {filtered.length} / {rows.length} · {status?.freshness || "UNAVAILABLE"} · 約每{" "}
              {status?.snapshotIntervalSec ?? 20} 秒 ·{" "}
              {status?.lastCycleAt ? new Date(status.lastCycleAt).toLocaleTimeString() : "—"}
            </p>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
            <UiDensityToggle density={density} onDensityChange={onDensity} />
            <Link to="/overview" className="nx-link">
              總覽
            </Link>
            <button
              type="button"
              className="nx-text-btn mobile-only"
              onClick={() => setFiltersOpen(true)}
            >
              篩選
            </button>
          </div>
        </header>
      ) : (
        <p className="nx-status-line muted sm">
          {filtered.length} / {rows.length} · {preset} 欄位 · {status?.freshness || "UNAVAILABLE"}
        </p>
      )}

      {error ? <div className="nx-banner-warn">{error}</div> : null}

      <div className={`nx-scanner-toolbar nx-scanner-toolbar-v1827 ${filtersOpen ? "open" : ""}`}>
        <div className="nx-scanner-filter-select">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="搜尋標的…"
            className="nx-search"
            aria-label="搜尋標的"
          />
          <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)} aria-label="排序">
            <option value="opportunity">機會分數</option>
            <option value="confirmation">確認程度</option>
            <option value="risk">風險程度</option>
            {advanced ? (
              <>
                <option value="oi">持倉變動</option>
                <option value="price">價格動能</option>
                <option value="turnover">交易活躍</option>
                <option value="liquidity">流動性</option>
                <option value="rankChange">排名變化</option>
              </>
            ) : null}
            <option value="newest">最新</option>
          </select>
          <select
            value={stageFilters.some((f) => f.id === filter) ? filter : ""}
            onChange={(e) => {
              const v = e.target.value as Filter | "";
              setFilter(v || "ALL");
            }}
            aria-label="階段篩選"
          >
            <option value="">階段：不限</option>
            {stageFilters.map((f) => (
              <option key={f.id} value={f.id}>
                {f.label}
              </option>
            ))}
          </select>
        </div>
        <div className="nx-filter-row desktop-only" role="group" aria-label="方向篩選">
          {primaryFilters.map((f) => (
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
              {[...primaryFilters, ...stageFilters].map((f) => (
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
              {showCol("opportunity") ? (
                <th className={sort === "opportunity" ? "sorted" : ""}>機會</th>
              ) : null}
              {showCol("confirmation") ? <th>確認</th> : null}
              {showCol("risk") ? <th>風險</th> : null}
              {showCol("price5m") ? <th>價 5m</th> : null}
              {showCol("oi5m") ? <th>持倉 5m</th> : null}
              {showCol("turnover") ? <th>活躍</th> : null}
              {showCol("rankChange") ? <th>排名</th> : null}
              {showCol("freshness") ? <th>新鮮度</th> : null}
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
                    {showCol("opportunity") ? (
                      <td className="mono">
                        {r.opportunityScore == null ? "UNAVAILABLE" : Math.round(r.opportunityScore)}
                      </td>
                    ) : null}
                    {showCol("confirmation") ? (
                      <td className="mono">
                        {r.confirmationScore == null ? "UNAVAILABLE" : Math.round(r.confirmationScore)}
                      </td>
                    ) : null}
                    {showCol("risk") ? (
                      <td className="mono">
                        {r.riskScore == null ? "UNAVAILABLE" : Math.round(r.riskScore)}
                      </td>
                    ) : null}
                    {showCol("price5m") ? (
                      <td className="mono">{fmtPct(r.priceChange5mPct)}</td>
                    ) : null}
                    {showCol("oi5m") ? (
                      <td className="mono">{fmtPct(r.oiChange5mPct)}</td>
                    ) : null}
                    {showCol("turnover") ? (
                      <td className="mono">{r.turnoverPace != null ? r.turnoverPace.toFixed(2) : "—"}</td>
                    ) : null}
                    {showCol("rankChange") ? <td className="mono">{rankMove(r)}</td> : null}
                    {showCol("freshness") ? <td>{r.freshness}</td> : null}
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
