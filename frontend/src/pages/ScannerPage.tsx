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

type SortKey = "opportunity" | "risk" | "price" | "newest" | "rankChange";

type SavedView = "default" | "risk_first" | "fresh";

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

/**
 * V18.2.9 professional scanner workspace.
 * Semantic filters · sticky defaults · row → context drawer (stay on page).
 */
export function ScannerPage({ hideHeader = false }: ScannerPageProps = {}) {
  const { rows, status, error, loading } = useScannerBoard();
  const [filter, setFilter] = useState<Filter>("ALL");
  const [sort, setSort] = useState<SortKey>("opportunity");
  const [q, setQ] = useState("");
  const [density, setDensity] = useState<UiDensity>(() => loadUiDensity());
  const [showAdvanced, setShowAdvanced] = useState(() => loadUiDensity() === "EXPERT");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [savedView, setSavedView] = useState<SavedView>("default");
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

  useEffect(() => {
    if (savedView === "risk_first") setSort("risk");
    else if (savedView === "fresh") setSort("newest");
    else setSort("opportunity");
  }, [savedView]);

  const filtered = useMemo(() => {
    let list = [...rows];
    const qq = q.trim().toUpperCase();
    if (qq) list = list.filter((r) => r.symbol.includes(qq));
    list = list.filter((r) => matchesFilter(r, filter));

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

  const selected = filtered.find((r) => r.id === selectedId) ?? null;

  const primaryFilters: { id: Filter; label: string }[] = [
    { id: "ALL", label: "全部" },
    { id: "WATCH_WORTHY", label: "值得關注" },
    { id: "WAITING", label: "等待" },
    { id: "BLOCKED", label: "阻擋" },
    { id: "HIGH_RISK", label: "高風險" },
    { id: "DEGRADED", label: "資料降級" },
  ];

  void density;

  return (
    <div className="page-stack" style={{ display: "contents" }} data-testid="scanner-v1828" data-product-gen="v18_2_9">
      {!hideHeader ? (
        <header className="v1829-panel v1829-col-12">
          <h1 className="v1829-page-title">全市場掃描</h1>
          <p className="v1829-page-sub" style={{ marginBottom: 0 }}>
            {filtered.length} / {rows.length} · {status?.freshness || "UNAVAILABLE"} · 約每{" "}
            {status?.snapshotIntervalSec ?? 20} 秒更新
          </p>
        </header>
      ) : null}

      {error ? <div className="nx-banner-warn v1829-panel v1829-col-12">{error}</div> : null}

      <div className={`v1829-scanner${selected ? "" : " no-drawer"}`}>
        <div className="v1829-scanner-main">
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
              <option value="risk_first">風險優先</option>
              <option value="fresh">最新優先</option>
            </select>
            <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)} aria-label="排序">
              <option value="opportunity">機會分數</option>
              <option value="risk">風險</option>
              <option value="price">價格變化</option>
              <option value="rankChange">排名變化</option>
              <option value="newest">最新</option>
            </select>
            <button
              type="button"
              className={`v1829-filter-chip${showAdvanced ? " active" : ""}`}
              onClick={() => setShowAdvanced((v) => !v)}
              aria-pressed={showAdvanced}
            >
              {showAdvanced ? "隱藏進階欄位" : "欄位控制"}
            </button>
            <button
              type="button"
              className="v1829-filter-chip mobile-only"
              onClick={() => setFiltersOpen(true)}
            >
              篩選
            </button>
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

          {filtersOpen ? (
            <div className="mobile-only" style={{ marginBottom: 12 }}>
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
              <button type="button" className="v1829-filter-chip" onClick={() => setFiltersOpen(false)}>
                關閉
              </button>
            </div>
          ) : null}

          <div className="desktop-only" style={{ overflowX: "auto" }}>
            <table className="v1829-scanner-table sticky-head">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>狀態</th>
                  <th>24h／變化</th>
                  <th>主要變化</th>
                  <th>風險</th>
                  <th>Data Trust</th>
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
                    <tr
                      key={r.id}
                      tabIndex={0}
                      className={selected?.id === r.id ? "is-selected" : undefined}
                      onClick={() => setSelectedId(selected?.id === r.id ? null : r.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") setSelectedId(selected?.id === r.id ? null : r.id);
                      }}
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
                        <span
                          className={
                            r.side === "LONG" ? "side-long" : r.side === "SHORT" ? "side-short" : ""
                          }
                        >
                          {STAGE_LABEL_ZH[r.stage]}
                        </span>
                      </td>
                      <td className="mono">{fmtPct(r.priceChange5mPct)}</td>
                      <td>{plainReason(r.reasons?.[0] || "—", simple)}</td>
                      <td className="mono">
                        {r.riskScore == null ? "UNAVAILABLE" : Math.round(r.riskScore)}
                      </td>
                      <td>{trustLabel(r)}</td>
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
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="mobile-only">
            {loading && filtered.length === 0 ? (
              <p className="muted">資料累積中…</p>
            ) : filtered.length === 0 ? (
              <p className="muted">篩選後無結果</p>
            ) : (
              filtered.map((r) => (
                <article
                  key={r.id}
                  style={{ padding: "12px 0", borderBottom: "1px solid var(--border)" }}
                  onClick={() => setSelectedId(selected?.id === r.id ? null : r.id)}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                    <Link
                      to={`/market/${r.symbol}`}
                      className="mono"
                      style={{ fontWeight: 600 }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {r.symbol.replace("USDT", "")}
                    </Link>
                    <WatchStarButton symbol={r.symbol} />
                  </div>
                  <p className="muted" style={{ margin: "4px 0", fontSize: "0.8125rem" }}>
                    {STAGE_LABEL_ZH[r.stage]} · 變化 {fmtPct(r.priceChange5mPct)} · 風險{" "}
                    {r.riskScore == null ? "—" : Math.round(r.riskScore)}
                  </p>
                  <p style={{ margin: 0, fontSize: "0.875rem" }}>
                    {plainReason(r.reasons?.[0] || "—", true)}
                  </p>
                  <p className="muted" style={{ margin: "4px 0 0", fontSize: "0.8125rem" }}>
                    {trustLabel(r)} · {agoLabel(r.lastUpdatedAt)}
                  </p>
                </article>
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
              {plainReason(selected.reasons?.[0] || "—", simple)}
            </p>
            <p className="muted" style={{ margin: "0 0 12px", fontSize: "0.8125rem" }}>
              {selected.conflicts?.[0]
                ? `反方：${plainReason(selected.conflicts[0], simple)}`
                : "無明顯衝突"}
              {showAdvanced ? ` · 價格 ${formatUsd(selected.currentPrice)}` : ""}
            </p>
            <div className="v1829-action-strip" style={{ paddingTop: 0 }}>
              <WatchStarButton symbol={selected.symbol} />
              <Link to={`/opportunities`} className="v1829-btn v1829-btn-secondary">
                決策工作區
              </Link>
              <Link to={`/market/${selected.symbol}`} className="v1829-btn v1829-btn-tertiary">
                深度分析 →
              </Link>
            </div>
          </aside>
        ) : null}
      </div>
    </div>
  );
}
