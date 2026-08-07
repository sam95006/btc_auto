import { Link } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
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
import { loadUiDensity, type UiDensity } from "../member/uiDensityPrefs";
import { memberDataTrustLabel } from "../market/marketMetricFunnel";

type Filter =
  | "ALL"
  | "WATCH_WORTHY"
  | "WAITING"
  | "BLOCKED"
  | "HIGH_RISK"
  | "DEGRADED";

type SortKey = "opportunity" | "risk" | "price" | "newest" | "rankChange" | "symbol";

type SavedView = "default" | "risk_first" | "fresh" | "watch";

type DensityPref = "comfortable" | "compact";

type ColId =
  | "symbol"
  | "stage"
  | "change"
  | "reason"
  | "risk"
  | "trust"
  | "updated"
  | "opportunity"
  | "confirm"
  | "oi"
  | "funding";

const BEGINNER_COLS: ColId[] = ["symbol", "stage", "change", "reason", "risk", "trust", "updated"];
const ADVANCED_EXTRA: ColId[] = ["opportunity", "confirm", "oi", "funding"];

const COL_LABEL: Record<ColId, string> = {
  symbol: "標的",
  stage: "狀態",
  change: "變化",
  reason: "主要原因",
  risk: "風險",
  trust: "資料品質",
  updated: "更新",
  opportunity: "機會",
  confirm: "確認",
  oi: "OI 5m",
  funding: "Funding",
};

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

function trustLabel(c: MarketCandidate): string {
  return memberDataTrustLabel({ scannerFreshness: c.freshness }).label_zh;
}

function matchesFilter(r: MarketCandidate, filter: Filter): boolean {
  if (filter === "ALL") return true;
  if (filter === "WATCH_WORTHY") {
    return (
      r.stage === "WATCHING" ||
      r.stage === "BUILDING" ||
      r.stage === "AWAITING_CONFIRMATION" ||
      r.stage === "CONFIRMED"
    );
  }
  if (filter === "WAITING") {
    return r.stage === "AWAITING_CONFIRMATION" || r.stage === "BUILDING";
  }
  if (filter === "BLOCKED") {
    return r.stage === "OVEREXTENDED" || (r.conflicts != null && r.conflicts.length > 0);
  }
  if (filter === "HIGH_RISK") {
    return r.stage === "OVEREXTENDED" || (r.riskScore != null && r.riskScore >= 70);
  }
  if (filter === "DEGRADED") {
    const f = String(r.freshness || "").toUpperCase();
    return f.includes("DEGRAD") || f === "STALE" || f === "DELAYED" || f.includes("PARTIAL");
  }
  return r.stage === (filter as CandidateStage);
}

type ScannerPageProps = {
  columnPreset?: string;
  hideHeader?: boolean;
};

const SAVED_KEY = "nexus.scanner.savedView.v1829";
const DENSITY_KEY = "nexus.scanner.density.v1829";
const COLS_KEY = "nexus.scanner.cols.v1829";

/**
 * V18.2.9 UX — professional scanner workstation.
 * Sticky filters + sticky header, sortable columns, saved views,
 * density, column selector. Desktop = table (not card-per-row).
 */
export function ScannerPage({ hideHeader = false }: ScannerPageProps = {}) {
  const { rows, status, error, loading } = useScannerBoard();
  const [filter, setFilter] = useState<Filter>("ALL");
  const [sort, setSort] = useState<SortKey>("opportunity");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [q, setQ] = useState("");
  const [uiDensity] = useState<UiDensity>(() => loadUiDensity());
  const [showAdvanced, setShowAdvanced] = useState(() => loadUiDensity() === "EXPERT");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [colsOpen, setColsOpen] = useState(false);
  const [savedView, setSavedView] = useState<SavedView>(() => {
    try {
      const v = localStorage.getItem(SAVED_KEY);
      if (v === "risk_first" || v === "fresh" || v === "watch" || v === "default") return v;
    } catch {
      /* ignore */
    }
    return "default";
  });
  const [density, setDensity] = useState<DensityPref>(() => {
    try {
      const v = localStorage.getItem(DENSITY_KEY);
      if (v === "compact" || v === "comfortable") return v;
    } catch {
      /* ignore */
    }
    return loadUiDensity() === "EXPERT" ? "compact" : "comfortable";
  });
  const [visibleCols, setVisibleCols] = useState<ColId[]>(() => {
    try {
      const raw = localStorage.getItem(COLS_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as ColId[];
        if (Array.isArray(parsed) && parsed.length) return parsed;
      }
    } catch {
      /* ignore */
    }
    return loadUiDensity() === "EXPERT" ? [...BEGINNER_COLS, ...ADVANCED_EXTRA] : [...BEGINNER_COLS];
  });

  useEffect(() => {
    const onDensityEvt = (e: Event) => {
      const d = (e as CustomEvent<UiDensity>).detail;
      if (d === "EXPERT") setShowAdvanced(true);
    };
    window.addEventListener("nexus-ui-density", onDensityEvt);
    return () => window.removeEventListener("nexus-ui-density", onDensityEvt);
  }, []);

  useEffect(() => {
    if (savedView === "risk_first") {
      setSort("risk");
      setFilter("HIGH_RISK");
    } else if (savedView === "fresh") {
      setSort("newest");
      setFilter("ALL");
    } else if (savedView === "watch") {
      setSort("opportunity");
      setFilter("WATCH_WORTHY");
    } else {
      setSort("opportunity");
      setFilter("ALL");
    }
    try {
      localStorage.setItem(SAVED_KEY, savedView);
    } catch {
      /* ignore */
    }
  }, [savedView]);

  useEffect(() => {
    try {
      localStorage.setItem(DENSITY_KEY, density);
    } catch {
      /* ignore */
    }
  }, [density]);

  useEffect(() => {
    try {
      localStorage.setItem(COLS_KEY, JSON.stringify(visibleCols));
    } catch {
      /* ignore */
    }
  }, [visibleCols]);

  const filtered = useMemo(() => {
    let list = [...rows];
    const qq = q.trim().toUpperCase();
    if (qq) list = list.filter((r) => r.symbol.includes(qq));
    list = list.filter((r) => matchesFilter(r, filter));

    const dir = sortDir === "asc" ? 1 : -1;
    const sorters: Record<SortKey, (a: MarketCandidate, b: MarketCandidate) => number> = {
      opportunity: (a, b) => ((b.opportunityScore ?? -1) - (a.opportunityScore ?? -1)) * dir,
      risk: (a, b) => ((b.riskScore ?? -1) - (a.riskScore ?? -1)) * dir,
      price: (a, b) =>
        (Math.abs(b.priceChange5mPct || 0) - Math.abs(a.priceChange5mPct || 0)) * dir,
      newest: (a, b) => ((b.firstSeenAt || 0) - (a.firstSeenAt || 0)) * dir,
      rankChange: (a, b) => ((b.rankDelta || 0) - (a.rankDelta || 0)) * dir,
      symbol: (a, b) => a.symbol.localeCompare(b.symbol) * dir,
    };
    list.sort(sorters[sort]);
    return list;
  }, [rows, filter, sort, sortDir, q]);

  const selected = filtered.find((r) => r.id === selectedId) ?? null;

  const primaryFilters: { id: Filter; label: string }[] = [
    { id: "ALL", label: "全部" },
    { id: "WATCH_WORTHY", label: "值得關注" },
    { id: "WAITING", label: "等待" },
    { id: "BLOCKED", label: "阻擋" },
    { id: "HIGH_RISK", label: "高風險" },
    { id: "DEGRADED", label: "資料品質" },
  ];

  const toggleSort = (key: SortKey) => {
    if (sort === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSort(key);
      setSortDir("desc");
    }
  };

  const toggleCol = (id: ColId) => {
    if (id === "symbol") return;
    setVisibleCols((cols) =>
      cols.includes(id) ? cols.filter((c) => c !== id) : [...cols, id],
    );
  };

  const activeCols = visibleCols.filter((c) =>
    showAdvanced || !ADVANCED_EXTRA.includes(c) ? true : false,
  );

  const sortHint = (key: SortKey) =>
    sort === key ? (sortDir === "asc" ? " ↑" : " ↓") : "";

  void uiDensity;

  return (
    <div
      className="page-stack"
      style={{ display: "contents" }}
      data-testid="scanner-v1828"
      data-product-gen="v18_2_9_ux"
      data-density={density}
    >
      {!hideHeader ? (
        <header className="v1829-panel v1829-col-12">
          <h1 className="v1829-page-title">全市場掃描</h1>
          <p className="v1829-page-sub" style={{ marginBottom: 0 }}>
            專業工作台 · {filtered.length} / {rows.length} · {status?.freshness || "更新未知"} · 約每{" "}
            {status?.snapshotIntervalSec ?? 20} 秒更新
          </p>
        </header>
      ) : null}

      {error ? <div className="nx-banner-warn v1829-panel v1829-col-12">{error}</div> : null}

      <div className={`v1829-scanner${selected ? "" : " no-drawer"}`}>
        <div className={`v1829-scanner-main density-${density}`}>
          <div className="v1829-scanner-sticky">
            <div className="v1829-scanner-toolbar">
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="搜尋標的…"
                aria-label="搜尋標的"
              />
              <select
                value={savedView}
                onChange={(e) => setSavedView(e.target.value as SavedView)}
                aria-label="已存檢視"
              >
                <option value="default">預設檢視</option>
                <option value="watch">關注優先</option>
                <option value="risk_first">風險優先</option>
                <option value="fresh">最新優先</option>
              </select>
              <button
                type="button"
                className={`v1829-filter-chip${density === "compact" ? " active" : ""}`}
                onClick={() => setDensity((d) => (d === "compact" ? "comfortable" : "compact"))}
              >
                {density === "compact" ? "緊湊" : "舒適"}
              </button>
              <button
                type="button"
                className={`v1829-filter-chip${showAdvanced ? " active" : ""}`}
                onClick={() => {
                  setShowAdvanced((v) => {
                    const next = !v;
                    if (next) {
                      setVisibleCols((cols) => {
                        const merged = [...cols];
                        for (const c of ADVANCED_EXTRA) {
                          if (!merged.includes(c)) merged.push(c);
                        }
                        return merged;
                      });
                    }
                    return next;
                  });
                }}
                aria-pressed={showAdvanced}
              >
                {showAdvanced ? "進階欄位開" : "進階欄位"}
              </button>
              <button
                type="button"
                className={`v1829-filter-chip${colsOpen ? " active" : ""}`}
                onClick={() => setColsOpen((v) => !v)}
              >
                欄位
              </button>
              <button
                type="button"
                className="v1829-filter-chip mobile-only"
                onClick={() => setFiltersOpen(true)}
              >
                篩選
              </button>
              <Link to="/alerts" className="v1829-btn v1829-btn-tertiary" style={{ minHeight: 28 }}>
                設警報
              </Link>
            </div>

            <div className="v1829-scanner-toolbar desktop-only" role="group" aria-label="語意篩選">
              {primaryFilters.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  className={`v1829-filter-chip${filter === f.id ? " active" : ""}`}
                  onClick={() => setFilter(f.id)}
                >
                  {f.label}
                </button>
              ))}
            </div>

            {colsOpen ? (
              <div className="v1829-col-picker" role="group" aria-label="欄位選擇">
                {([...BEGINNER_COLS, ...ADVANCED_EXTRA] as ColId[]).map((id) => (
                  <label key={id} className="v1829-col-picker-item">
                    <input
                      type="checkbox"
                      checked={visibleCols.includes(id)}
                      disabled={id === "symbol"}
                      onChange={() => toggleCol(id)}
                    />
                    {COL_LABEL[id]}
                  </label>
                ))}
              </div>
            ) : null}
          </div>

          {filtersOpen ? (
            <div className="v1829-filter-sheet mobile-only" role="dialog" aria-label="篩選">
              <div className="v1829-scanner-toolbar">
                {primaryFilters.map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    className={`v1829-filter-chip${filter === f.id ? " active" : ""}`}
                    onClick={() => {
                      setFilter(f.id);
                      setFiltersOpen(false);
                    }}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
              <button type="button" className="v1829-btn v1829-btn-secondary" onClick={() => setFiltersOpen(false)}>
                關閉篩選
              </button>
            </div>
          ) : null}

          <div className="desktop-only v1829-scanner-table-wrap">
            <table className="v1829-scanner-table sticky-head">
              <thead>
                <tr>
                  {activeCols.includes("symbol") ? (
                    <th>
                      <button type="button" className="th-sort" onClick={() => toggleSort("symbol")}>
                        {COL_LABEL.symbol}
                        {sortHint("symbol")}
                      </button>
                    </th>
                  ) : null}
                  {activeCols.includes("stage") ? <th>{COL_LABEL.stage}</th> : null}
                  {activeCols.includes("change") ? (
                    <th>
                      <button type="button" className="th-sort" onClick={() => toggleSort("price")}>
                        {COL_LABEL.change}
                        {sortHint("price")}
                      </button>
                    </th>
                  ) : null}
                  {activeCols.includes("reason") ? <th>{COL_LABEL.reason}</th> : null}
                  {activeCols.includes("risk") ? (
                    <th>
                      <button type="button" className="th-sort" onClick={() => toggleSort("risk")}>
                        {COL_LABEL.risk}
                        {sortHint("risk")}
                      </button>
                    </th>
                  ) : null}
                  {activeCols.includes("trust") ? <th>{COL_LABEL.trust}</th> : null}
                  {activeCols.includes("updated") ? (
                    <th>
                      <button type="button" className="th-sort" onClick={() => toggleSort("newest")}>
                        {COL_LABEL.updated}
                        {sortHint("newest")}
                      </button>
                    </th>
                  ) : null}
                  {activeCols.includes("opportunity") ? (
                    <th>
                      <button type="button" className="th-sort" onClick={() => toggleSort("opportunity")}>
                        {COL_LABEL.opportunity}
                        {sortHint("opportunity")}
                      </button>
                    </th>
                  ) : null}
                  {activeCols.includes("confirm") ? <th>{COL_LABEL.confirm}</th> : null}
                  {activeCols.includes("oi") ? <th>{COL_LABEL.oi}</th> : null}
                  {activeCols.includes("funding") ? <th>{COL_LABEL.funding}</th> : null}
                  <th />
                </tr>
              </thead>
              <tbody>
                {loading && filtered.length === 0 ? (
                  <tr>
                    <td colSpan={activeCols.length + 1} className="muted">
                      資料累積中…
                    </td>
                  </tr>
                ) : filtered.length === 0 ? (
                  <tr>
                    <td colSpan={activeCols.length + 1} className="muted">
                      篩選後無結果（不會用假候選填空）
                    </td>
                  </tr>
                ) : (
                  filtered.map((r) => (
                    <tr
                      key={r.id}
                      tabIndex={0}
                      className={selected?.id === r.id ? "is-selected" : undefined}
                      onClick={() => setSelectedId(selected?.id === r.id ? null : r.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") setSelectedId(selected?.id === r.id ? null : r.id);
                      }}
                    >
                      {activeCols.includes("symbol") ? (
                        <td>
                          <Link
                            to={`/market/${r.symbol}`}
                            className="mono"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {r.symbol.replace("USDT", "")}
                          </Link>
                        </td>
                      ) : null}
                      {activeCols.includes("stage") ? (
                        <td>
                          <span
                            className={
                              r.side === "LONG" ? "side-long" : r.side === "SHORT" ? "side-short" : ""
                            }
                          >
                            {STAGE_LABEL_ZH[r.stage]}
                          </span>
                        </td>
                      ) : null}
                      {activeCols.includes("change") ? (
                        <td className="mono">{fmtPct(r.priceChange5mPct)}</td>
                      ) : null}
                      {activeCols.includes("reason") ? (
                        <td>{plainReason(r.reasons?.[0] || "—", !showAdvanced)}</td>
                      ) : null}
                      {activeCols.includes("risk") ? (
                        <td className="mono">
                          {r.riskScore == null ? "—" : Math.round(r.riskScore)}
                        </td>
                      ) : null}
                      {activeCols.includes("trust") ? <td>{trustLabel(r)}</td> : null}
                      {activeCols.includes("updated") ? (
                        <td className="mono muted">{agoLabel(r.lastUpdatedAt)}</td>
                      ) : null}
                      {activeCols.includes("opportunity") ? (
                        <td className="mono">
                          {r.opportunityScore == null ? "—" : Math.round(r.opportunityScore)}
                        </td>
                      ) : null}
                      {activeCols.includes("confirm") ? (
                        <td className="mono">
                          {r.confirmationScore == null ? "—" : Math.round(r.confirmationScore)}
                        </td>
                      ) : null}
                      {activeCols.includes("oi") ? (
                        <td className="mono">{fmtPct(r.oiChange5mPct)}</td>
                      ) : null}
                      {activeCols.includes("funding") ? (
                        <td className="mono">
                          {r.fundingRate == null
                            ? "—"
                            : `${(r.fundingRate * 100).toFixed(4)}%`}
                        </td>
                      ) : null}
                      <td onClick={(e) => e.stopPropagation()}>
                        <WatchStarButton symbol={r.symbol} />
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="mobile-only v1829-scanner-mobile">
            {loading && filtered.length === 0 ? (
              <p className="muted">資料累積中…</p>
            ) : filtered.length === 0 ? (
              <p className="muted">篩選後無結果</p>
            ) : (
              filtered.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  className={`v1829-scanner-compact-row${selected?.id === r.id ? " is-selected" : ""}`}
                  onClick={() => setSelectedId(selected?.id === r.id ? null : r.id)}
                >
                  <span className="mono sym">{r.symbol.replace("USDT", "")}</span>
                  <span className="stage">{STAGE_LABEL_ZH[r.stage]}</span>
                  <span className="mono chg">{fmtPct(r.priceChange5mPct)}</span>
                  <span className="reason">{plainReason(r.reasons?.[0] || "—", true)}</span>
                </button>
              ))
            )}
          </div>
        </div>

        {selected ? (
          <aside className="v1829-scanner-drawer" aria-label="掃描上下文" data-testid="scanner-context-drawer">
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 12 }}>
              <strong className="mono" style={{ fontSize: "1.15rem" }}>
                {selected.symbol.replace("USDT", "")}
              </strong>
              <button
                type="button"
                className="v1829-btn v1829-btn-tertiary"
                onClick={() => setSelectedId(null)}
              >
                關閉
              </button>
            </div>
            <p className="muted" style={{ margin: "0 0 10px", fontSize: "0.875rem" }}>
              {sideLabelZh(selected.side)} · {STAGE_LABEL_ZH[selected.stage]} · {trustLabel(selected)}
            </p>
            <p style={{ margin: "0 0 10px", fontSize: "0.875rem" }}>
              {plainReason(selected.reasons?.[0] || "—", !showAdvanced)}
            </p>
            <p className="muted" style={{ margin: "0 0 12px", fontSize: "0.8125rem" }}>
              {selected.conflicts?.[0]
                ? `反對：${plainReason(selected.conflicts[0], !showAdvanced)}`
                : "無明顯衝突"}
              {showAdvanced ? ` · 價格 ${formatUsd(selected.currentPrice)}` : ""}
            </p>
            <div className="v1829-action-strip" style={{ paddingTop: 0 }}>
              <WatchStarButton symbol={selected.symbol} />
              <Link to="/alerts" className="v1829-btn v1829-btn-secondary">
                設警報
              </Link>
              <Link to="/opportunities" className="v1829-btn v1829-btn-secondary">
                決策工作區
              </Link>
              <Link to={`/market/${selected.symbol}`} className="v1829-btn v1829-btn-tertiary">
                深入分析 →
              </Link>
            </div>
          </aside>
        ) : null}
      </div>
    </div>
  );
}
