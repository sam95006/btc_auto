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
import { loadUiDensity, type UiDensity } from "../member/uiDensityPrefs";

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

type SortKey = "opportunity" | "risk" | "price" | "newest" | "rankChange";

function fmtPct(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "UNAVAILABLE";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function agoLabel(ts?: number | null) {
  if (!ts) return "—";
  const sec = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.round(sec / 60)}m`;
  return `${Math.round(sec / 3600)}h`;
}

type ScannerPageProps = {
  columnPreset?: string;
  hideHeader?: boolean;
};

/**
 * V18.2.8 professional scanner.
 * Default columns: Symbol 狀態 變化 主要原因 風險 資料 更新
 * Advanced columns revealable; no badge walls; no chrome density toggle.
 */
export function ScannerPage({ hideHeader = false }: ScannerPageProps = {}) {
  const { rows, status, error, loading } = useScannerBoard();
  const [filter, setFilter] = useState<Filter>("ALL");
  const [sort, setSort] = useState<SortKey>("opportunity");
  const [q, setQ] = useState("");
  const [density, setDensity] = useState<UiDensity>(() => loadUiDensity());
  const [showAdvanced, setShowAdvanced] = useState(() => loadUiDensity() === "EXPERT");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const simple = !showAdvanced;

  useEffect(() => {
    const onDensityEvt = (e: Event) => {
      const d = (e as CustomEvent<UiDensity>).detail;
      if (d === "SIMPLE" || d === "EXPERT") {
        setDensity(d);
        if (d === "EXPERT") setShowAdvanced(true);
      }
    };
    window.addEventListener("nexus-ui-density", onDensityEvt);
    return () => window.removeEventListener("nexus-ui-density", onDensityEvt);
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
      opportunity: (a, b) => (b.opportunityScore ?? -1) - (a.opportunityScore ?? -1),
      risk: (a, b) => (b.riskScore ?? -1) - (a.riskScore ?? -1),
      price: (a, b) => Math.abs(b.priceChange5mPct || 0) - Math.abs(a.priceChange5mPct || 0),
      newest: (a, b) => (b.firstSeenAt || 0) - (a.firstSeenAt || 0),
      rankChange: (a, b) => (b.rankDelta || 0) - (a.rankDelta || 0),
    };
    list.sort(sorters[sort]);
    return list;
  }, [rows, filter, sort, q]);

  const primaryFilters: { id: Filter; label: string }[] = [
    { id: "ALL", label: "全部" },
    { id: "LONG", label: "偏多" },
    { id: "SHORT", label: "偏空" },
    { id: "CONFIRMED", label: "已確認" },
    { id: "HIGH_RISK", label: "高風險" },
    { id: "WATCHING", label: "觀察" },
    { id: "AWAITING_CONFIRMATION", label: "待確認" },
  ];

  void density;

  return (
    <div className="page-stack" style={{ display: "contents" }} data-testid="scanner-v1828">
      {!hideHeader ? (
        <header className="v1828-ov-block">
          <h1 className="v1828-page-title">全市場掃描</h1>
          <p className="v1828-page-sub">
            {filtered.length} / {rows.length} · {status?.freshness || "UNAVAILABLE"} · 約每{" "}
            {status?.snapshotIntervalSec ?? 20} 秒更新
          </p>
        </header>
      ) : null}

      {error ? <div className="nx-banner-warn v1828-ov-block">{error}</div> : null}

      <div className="v1828-ov-block">
        <div className="v1828-scanner-toolbar">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="搜尋標的…"
            aria-label="搜尋標的"
          />
          <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)} aria-label="排序">
            <option value="opportunity">機會分數</option>
            <option value="risk">風險</option>
            <option value="price">價格變化</option>
            <option value="rankChange">排名變化</option>
            <option value="newest">最新</option>
          </select>
          <button
            type="button"
            className={`v1828-filter-chip${showAdvanced ? " active" : ""}`}
            onClick={() => setShowAdvanced((v) => !v)}
            aria-pressed={showAdvanced}
          >
            {showAdvanced ? "隱藏進階欄位" : "顯示進階欄位"}
          </button>
          <button
            type="button"
            className="v1828-filter-chip mobile-only"
            onClick={() => setFiltersOpen(true)}
          >
            篩選
          </button>
        </div>

        <div className="v1828-scanner-toolbar desktop-only" role="group" aria-label="篩選">
          {primaryFilters.map((f) => (
            <button
              key={f.id}
              type="button"
              className={`v1828-filter-chip${filter === f.id ? " active" : ""}`}
              onClick={() => setFilter(f.id)}
            >
              {f.label}
            </button>
          ))}
        </div>

        {filtersOpen ? (
          <div className="mobile-only" style={{ marginBottom: 12 }}>
            <div className="v1828-scanner-toolbar">
              {primaryFilters.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  className={`v1828-filter-chip${filter === f.id ? " active" : ""}`}
                  onClick={() => {
                    setFilter(f.id);
                    setFiltersOpen(false);
                  }}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <button type="button" className="v1828-filter-chip" onClick={() => setFiltersOpen(false)}>
              關閉
            </button>
          </div>
        ) : null}

        {/* Desktop table — default professional columns */}
        <div className="desktop-only" style={{ overflowX: "auto" }}>
          <table className="v1828-scanner-table sticky-head">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>狀態</th>
                <th>變化</th>
                <th>主要原因</th>
                <th>風險</th>
                <th>資料</th>
                <th>更新</th>
                {showAdvanced ? (
                  <>
                    <th>機會</th>
                    <th>確認</th>
                    <th>OI 5m</th>
                    <th>Funding</th>
                  </>
                ) : null}
                <th />
              </tr>
            </thead>
            <tbody>
              {loading && filtered.length === 0 ? (
                <tr>
                  <td colSpan={showAdvanced ? 12 : 8} className="muted">
                    資料累積中…
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={showAdvanced ? 12 : 8} className="muted">
                    篩選後無結果（不會用假候選填空）
                  </td>
                </tr>
              ) : (
                filtered.map((r) => (
                  <Fragment key={r.id}>
                    <tr
                      tabIndex={0}
                      onClick={() => setExpanded(expanded === r.id ? null : r.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") setExpanded(expanded === r.id ? null : r.id);
                      }}
                      style={{ cursor: "pointer" }}
                    >
                      <td>
                        <Link
                          to={`/market/${r.symbol}`}
                          className="mono"
                          onClick={(e) => e.stopPropagation()}
                        >
                          {r.symbol.replace("USDT", "")}
                        </Link>
                      </td>
                      <td>
                        <span className={r.side === "LONG" ? "side-long" : r.side === "SHORT" ? "side-short" : ""}>
                          {STAGE_LABEL_ZH[r.stage]}
                        </span>
                      </td>
                      <td className="mono">{fmtPct(r.priceChange5mPct)}</td>
                      <td>{plainReason(r.reasons?.[0] || "—", simple)}</td>
                      <td className="mono">
                        {r.riskScore == null ? "UNAVAILABLE" : Math.round(r.riskScore)}
                      </td>
                      <td>{r.freshness || "UNAVAILABLE"}</td>
                      <td className="mono muted">{agoLabel(r.lastUpdatedAt)}</td>
                      {showAdvanced ? (
                        <>
                          <td className="mono">
                            {r.opportunityScore == null
                              ? "UNAVAILABLE"
                              : Math.round(r.opportunityScore)}
                          </td>
                          <td className="mono">
                            {r.confirmationScore == null
                              ? "UNAVAILABLE"
                              : Math.round(r.confirmationScore)}
                          </td>
                          <td className="mono">{fmtPct(r.oiChange5mPct)}</td>
                          <td className="mono">
                            {r.fundingRate == null
                              ? "UNAVAILABLE"
                              : `${(r.fundingRate * 100).toFixed(4)}%`}
                          </td>
                        </>
                      ) : null}
                      <td onClick={(e) => e.stopPropagation()}>
                        <WatchStarButton symbol={r.symbol} />
                      </td>
                    </tr>
                    {expanded === r.id ? (
                      <tr>
                        <td colSpan={showAdvanced ? 12 : 8}>
                          <p className="muted sm">
                            {sideLabelZh(r.side)} ·{" "}
                            {r.conflicts?.[0]
                              ? `風險：${plainReason(r.conflicts[0], simple)}`
                              : "無明顯衝突"}
                            {showAdvanced ? ` · 價格 ${formatUsd(r.currentPrice)}` : ""}
                          </p>
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
        <div className="mobile-only">
          {loading && filtered.length === 0 ? (
            <p className="muted">資料累積中…</p>
          ) : filtered.length === 0 ? (
            <p className="muted">篩選後無結果</p>
          ) : (
            filtered.map((r) => (
              <article
                key={r.id}
                style={{
                  padding: "12px 0",
                  borderBottom: "1px solid var(--nx-border)",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <Link to={`/market/${r.symbol}`} className="mono" style={{ fontWeight: 600 }}>
                    {r.symbol.replace("USDT", "")}
                  </Link>
                  <WatchStarButton symbol={r.symbol} />
                </div>
                <p className="muted sm" style={{ margin: "4px 0" }}>
                  {STAGE_LABEL_ZH[r.stage]} · 變化 {fmtPct(r.priceChange5mPct)} · 風險{" "}
                  {r.riskScore == null ? "UNAVAILABLE" : Math.round(r.riskScore)}
                </p>
                <p style={{ margin: 0, fontSize: "0.875rem" }}>
                  {plainReason(r.reasons?.[0] || "—", true)}
                </p>
                <p className="muted sm" style={{ margin: "4px 0 0" }}>
                  {r.freshness || "UNAVAILABLE"} · {agoLabel(r.lastUpdatedAt)}
                </p>
              </article>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
