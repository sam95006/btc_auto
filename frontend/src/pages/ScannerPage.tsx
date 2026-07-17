import { Link } from "react-router-dom";
import { useMemo, useState } from "react";
import {
  STAGE_LABEL_ZH,
  sideLabelZh,
  type CandidateStage,
  type MarketCandidate,
} from "../market/scannerApi";
import { useScannerBoard } from "../market/useMarketScanner";
import { formatUsd } from "../market/freshness";

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

/**
 * Full market scanner board — server ranking snapshot only.
 */
export function ScannerPage() {
  const { rows, status, error, loading } = useScannerBoard();
  const [filter, setFilter] = useState<Filter>("ALL");
  const [sort, setSort] = useState<SortKey>("opportunity");
  const [q, setQ] = useState("");
  const [advanced, setAdvanced] = useState(false);

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
    <div className="page-stack nx-scanner-page">
      <header className="nx-ov-header">
        <h1 className="nx-page-title">全市場掃描器</h1>
        <p className="nx-status-line">
          {status?.symbolCount ?? "—"} symbols · {status?.freshness || "—"} · 候選約每{" "}
          {status?.snapshotIntervalSec ?? 20} 秒重新掃描 · Research only · No trading
        </p>
        <div className="nx-ov-meta">
          <Link to="/overview">← 總覽</Link>
          <button type="button" className="nx-text-btn" onClick={() => setAdvanced((v) => !v)}>
            {advanced ? "簡易" : "進階"}
          </button>
        </div>
      </header>

      {error ? <div className="nx-banner-warn">{error}</div> : null}

      <div className="nx-filter-row">
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

      <div className="nx-sort-row">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="搜尋 symbol…"
          className="nx-search"
        />
        <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
          <option value="opportunity">機會分數</option>
          <option value="confirmation">確認程度</option>
          <option value="risk">風險程度</option>
          <option value="oi">OI 變動</option>
          <option value="price">價格動能</option>
          <option value="turnover">交易活躍</option>
          <option value="liquidity">流動性</option>
          <option value="newest">最新</option>
          <option value="rankChange">排名變化</option>
        </select>
      </div>

      <div className="nx-scanner-table-wrap">
        <table className="nx-scanner-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>方向</th>
              <th>階段</th>
              <th>機會</th>
              <th>確認</th>
              <th>風險</th>
              <th>價格</th>
              <th>價變</th>
              <th>OI</th>
              {advanced ? (
                <>
                  <th>Funding</th>
                  <th>Spread</th>
                </>
              ) : null}
              <th>理由</th>
              <th>新鮮度</th>
            </tr>
          </thead>
          <tbody>
            {loading && filtered.length === 0 ? (
              <tr>
                <td colSpan={12} className="muted">
                  資料累積中…
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={12} className="muted">
                  無符合條件的市場機會
                </td>
              </tr>
            ) : (
              filtered.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link to={`/market/${r.symbol}`} className="mono">
                      {r.symbol}
                    </Link>
                  </td>
                  <td>{sideLabelZh(r.side)}</td>
                  <td>{STAGE_LABEL_ZH[r.stage]}</td>
                  <td className="mono">{Math.round(r.opportunityScore)}</td>
                  <td className="mono">{Math.round(r.confirmationScore)}</td>
                  <td className="mono">{Math.round(r.riskScore)}</td>
                  <td className="mono">{formatUsd(r.currentPrice)}</td>
                  <td className="mono">{fmtPct(r.priceChange5mPct)}</td>
                  <td className="mono">{fmtPct(r.oiChange5mPct)}</td>
                  {advanced ? (
                    <>
                      <td className="mono">
                        {r.fundingRate != null ? (r.fundingRate * 100).toFixed(4) + "%" : "—"}
                      </td>
                      <td className="mono">
                        {r.spreadBps != null ? r.spreadBps.toFixed(1) : "—"}
                      </td>
                    </>
                  ) : null}
                  <td className="nx-reason-cell">
                    {r.reasons?.[0] || "—"}
                    {advanced && r.conflicts?.[0] ? (
                      <div className="muted">衝突：{r.conflicts[0]}</div>
                    ) : null}
                  </td>
                  <td>{r.freshness}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
