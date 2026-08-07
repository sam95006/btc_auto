import { Link } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import {
  STAGE_LABEL_ZH,
  plainReason,
  sideLabelZh,
  type CandidateStage,
  type MarketCandidate,
} from "../../market/scannerApi";
import { useScannerBoard } from "../../market/useMarketScanner";
import { formatUsd } from "../../market/freshness";
import { WatchStarButton } from "../../components/WatchStarButton";
import { loadUiDensity, type UiDensity } from "../../member/uiDensityPrefs";
import { memberDataTrustLabel } from "../../market/marketMetricFunnel";

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

const SAVED_KEY = "nexus.scanner.savedView.v2";
const DENSITY_KEY = "nexus.scanner.density.v2";
const COLS_KEY = "nexus.scanner.cols.v2";

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

/**
 * Product V2 Scanner — terminal table workspace.
 * Sticky toolbar/header, sorting, beginner vs advanced columns. No desktop card list.
 */
export function ScannerPageV2() {
  const { rows, status, error, loading } = useScannerBoard();
  const [filter, setFilter] = useState<Filter>("ALL");
  const [sort, setSort] = useState<SortKey>("opportunity");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [q, setQ] = useState("");
  const [uiDensity] = useState<UiDensity>(() => loadUiDensity());
  const [showAdvanced, setShowAdvanced] = useState(() => loadUiDensity() === "EXPERT");
  const [selectedId, setSelectedId] = useState<string | null>(null);
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
    setVisibleCols((cols) => (cols.includes(id) ? cols.filter((c) => c !== id) : [...cols, id]));
  };

  const activeCols = visibleCols.filter((c) =>
    showAdvanced || !ADVANCED_EXTRA.includes(c) ? true : false,
  );
  const sortHint = (key: SortKey) => (sort === key ? (sortDir === "asc" ? " ↑" : " ↓") : "");
  void uiDensity;

  const renderCell = (c: MarketCandidate, col: ColId) => {
    switch (col) {
      case "symbol":
        return (
          <td key={col}>
            <Link to={`/market/${c.symbol}`} className="mono">
              {c.symbol.replace("USDT", "")}
            </Link>{" "}
            <span className="muted">{sideLabelZh(c.side)}</span>
          </td>
        );
      case "stage":
        return <td key={col}>{STAGE_LABEL_ZH[c.stage] || c.stage}</td>;
      case "change":
        return (
          <td key={col} className={`mono ${(c.priceChange5mPct ?? 0) >= 0 ? "pos" : "neg"}`}>
            {fmtPct(c.priceChange5mPct)}
          </td>
        );
      case "reason":
        return <td key={col}>{plainReason(c.reasons?.[0] || "—", !showAdvanced)}</td>;
      case "risk":
        return (
          <td key={col} className={`mono ${(c.riskScore ?? 0) >= 70 ? "neg" : ""}`}>
            {c.riskScore == null ? "—" : Math.round(c.riskScore)}
          </td>
        );
      case "trust":
        return <td key={col}>{trustLabel(c)}</td>;
      case "updated":
        return <td key={col} className="mono muted">{agoLabel(c.lastUpdatedAt)}</td>;
      case "opportunity":
        return <td key={col} className="mono">{c.opportunityScore == null ? "—" : Math.round(c.opportunityScore)}</td>;
      case "confirm":
        return <td key={col} className="mono">{c.confirmationScore == null ? "—" : Math.round(c.confirmationScore)}</td>;
      case "oi":
        return <td key={col} className="mono">{fmtPct(c.oiChange5mPct)}</td>;
      case "funding":
        return (
          <td key={col} className="mono">
            {c.fundingRate == null ? "—" : `${(c.fundingRate * 100).toFixed(4)}%`}
          </td>
        );
      default:
        return <td key={col}>—</td>;
    }
  };

  const colSortKey: Partial<Record<ColId, SortKey>> = {
    symbol: "symbol",
    risk: "risk",
    opportunity: "opportunity",
    change: "price",
    updated: "newest",
  };

  return (
    <div data-testid="product-v2-scanner" data-nexus-product-generation="2" data-density={density}>
      <header>
        <h1 className="mp2-page-title">掃描器</h1>
        <p className="mp2-page-sub">
          終端表格工作台 · {filtered.length} / {rows.length} · {status?.freshness || "更新未知"} · 約每{" "}
          {status?.snapshotIntervalSec ?? 20} 秒
        </p>
      </header>

      {error ? <div className="mp2-banner">{error}</div> : null}

      <div className="mp2-scanner-toolbar">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜尋標的…" aria-label="搜尋標的" />
        <select value={savedView} onChange={(e) => setSavedView(e.target.value as SavedView)} aria-label="已存檢視">
          <option value="default">預設檢視</option>
          <option value="watch">關注優先</option>
          <option value="risk_first">風險優先</option>
          <option value="fresh">最新優先</option>
        </select>
        <select value={density} onChange={(e) => setDensity(e.target.value as DensityPref)} aria-label="密度">
          <option value="comfortable">舒適</option>
          <option value="compact">緊湊</option>
        </select>
        <button type="button" className="mp2-btn" onClick={() => setShowAdvanced((v) => !v)}>
          {showAdvanced ? "進階欄位 ON" : "進階欄位"}
        </button>
        <div className="mp2-chip-row" role="group" aria-label="篩選">
          {primaryFilters.map((f) => (
            <button
              key={f.id}
              type="button"
              className={filter === f.id ? "active" : undefined}
              onClick={() => setFilter(f.id)}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {showAdvanced ? (
        <div className="mp2-chip-row" style={{ marginBottom: 8 }} aria-label="欄位">
          {[...BEGINNER_COLS, ...ADVANCED_EXTRA].map((id) => (
            <button
              key={id}
              type="button"
              className={visibleCols.includes(id) ? "active" : undefined}
              onClick={() => toggleCol(id)}
              disabled={id === "symbol"}
            >
              {COL_LABEL[id]}
            </button>
          ))}
        </div>
      ) : null}

      <div className="mp2-scanner-wrap">
        <table className="mp2-table" data-testid="scanner-table">
          <thead>
            <tr>
              {activeCols.map((col) => {
                const sk = colSortKey[col];
                return (
                  <th
                    key={col}
                    className={sk ? "sortable" : undefined}
                    onClick={sk ? () => toggleSort(sk) : undefined}
                  >
                    {COL_LABEL[col]}
                    {sk ? sortHint(sk) : ""}
                  </th>
                );
              })}
              <th />
            </tr>
          </thead>
          <tbody>
            {loading && !filtered.length ? (
              <tr>
                <td colSpan={activeCols.length + 1} className="muted">
                  載入中…
                </td>
              </tr>
            ) : null}
            {!loading && !filtered.length ? (
              <tr>
                <td colSpan={activeCols.length + 1} className="muted">
                  無符合條件的列
                </td>
              </tr>
            ) : null}
            {filtered.map((c) => (
              <tr
                key={c.id}
                className={selected?.id === c.id ? "is-selected" : undefined}
                onClick={() => setSelectedId(c.id)}
              >
                {activeCols.map((col) => renderCell(c, col))}
                <td>
                  <WatchStarButton symbol={c.symbol} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected ? (
        <div className="mp2-section" style={{ marginTop: 16 }}>
          <p className="mp2-kicker">選取列</p>
          <strong className="mono">{selected.symbol.replace("USDT", "")}</strong>
          <span className="muted"> · {formatUsd(selected.currentPrice)}</span>
          <div className="mp2-actions">
            <Link to={`/opportunities`} className="mp2-btn mp2-btn-primary">
              決策工作區
            </Link>
            <Link to={`/market/${selected.symbol}`} className="mp2-btn">
              標的詳情
            </Link>
          </div>
        </div>
      ) : null}
    </div>
  );
}
