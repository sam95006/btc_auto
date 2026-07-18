import { Link } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import { fetchSectors, fetchSectorsStatus, fetchSectorSymbols, type SectorRow } from "../../market/sectorApi";

function fmtPct(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

/**
 * Crypto sector overview — breadth + deep-scan coverage (Phase 3).
 */
export function CryptoSectorsPage() {
  const [rows, setRows] = useState<SectorRow[]>([]);
  const [status, setStatus] = useState<Awaited<ReturnType<typeof fetchSectorsStatus>> | null>(null);
  const [sort, setSort] = useState("performance");
  const [filter, setFilter] = useState("ALL");
  const [open, setOpen] = useState<string | null>(null);
  const [members, setMembers] = useState<Record<string, unknown>[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const stateParam =
          filter === "ALL" || filter.startsWith("HAS_") ? undefined : filter;
        const [st, body] = await Promise.all([
          fetchSectorsStatus(),
          fetchSectors(sort, stateParam),
        ]);
        if (!alive) return;
        setStatus(st);
        setRows(body.sectors || []);
        setError(null);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "load_failed");
      }
    };
    void load();
    const id = window.setInterval(() => void load(), 20000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [sort, filter]);

  const filters = useMemo(
    () => [
      { id: "ALL", label: "全部" },
      { id: "HOT", label: "熱度上升" },
      { id: "ACTIVE", label: "資金活躍" },
      { id: "MIXED", label: "多空分歧" },
      { id: "WEAK", label: "動能偏弱" },
      { id: "RISKY", label: "風險升高" },
      { id: "COLLECTING", label: "資料累積中" },
      { id: "HAS_LONG", label: "有做多候選" },
      { id: "HAS_SHORT", label: "有做空候選" },
      { id: "HAS_CONFIRMED", label: "有已確認" },
    ],
    [],
  );

  const visible = useMemo(() => {
    if (filter === "HAS_LONG") return rows.filter((r) => r.longCandidateCount > 0);
    if (filter === "HAS_SHORT") return rows.filter((r) => r.shortCandidateCount > 0);
    if (filter === "HAS_CONFIRMED") return rows.filter((r) => r.confirmedCandidateCount > 0);
    return rows;
  }, [rows, filter]);

  const toggle = async (id: string) => {
    if (open === id) {
      setOpen(null);
      return;
    }
    setOpen(id);
    try {
      const body = await fetchSectorSymbols(id, 40);
      setMembers(body.symbols || []);
    } catch {
      setMembers([]);
    }
  };

  return (
    <div className="page-stack nx-sectors-page nx-p3">
      <header className="nx-ov-header">
        <h1 className="nx-page-title">幣種版塊</h1>
        <p className="nx-status-line">
          市場涵蓋 {status?.breadthMarketCount ?? "—"} · 深度掃描 {status?.deepScanCount ?? "—"} · 已分類{" "}
          {status?.classifiedSymbolCount ?? "—"} · 未分類 {status?.unclassifiedSymbolCount ?? "—"} ·{" "}
          {status?.freshness || "—"}
        </p>
        <p className="muted sm">
          廣度層用於版塊排行；深度層（約 80）提供 5m 持倉／候選。研究模式 · 不執行交易。
        </p>
        <div className="nx-ov-meta">
          <Link to="/overview">← 總覽</Link>
          <Link to="/crypto/oi">OI 排行</Link>
          <Link to="/crypto/funding">Funding</Link>
          <Link to="/crypto/price-oi">Price／OI</Link>
        </div>
      </header>

      {error ? <div className="nx-banner-warn">{error}</div> : null}

      <div className="nx-filter-row">
        {filters.map((f) => (
          <button key={f.id} type="button" className={filter === f.id ? "active" : ""} onClick={() => setFilter(f.id)}>
            {f.label}
          </button>
        ))}
      </div>
      <div className="nx-sort-row">
        <select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="排序">
          <option value="performance">績效</option>
          <option value="breadth">廣度</option>
          <option value="oi">持倉變動</option>
          <option value="turnover">成交活躍</option>
          <option value="candidates">候選數</option>
          <option value="risk">風險</option>
          <option value="alphabetical">名稱</option>
        </select>
      </div>

      <ul className="nx-sector-list">
        {visible.length === 0 ? (
          <li className="muted">尚無版塊資料或篩選無結果</li>
        ) : (
          visible.map((s) => (
            <li key={s.id} className="nx-sector-card">
              <button type="button" className="nx-sector-head" onClick={() => void toggle(s.id)}>
                <span className="nx-sector-name">{s.nameZhTW}</span>
                <span className="nx-sector-state">{s.sectorStateLabelZh}</span>
                <span className="mono">{fmtPct(s.turnoverWeightedReturn24h)}</span>
                <span className="muted sm">
                  廣度 {s.risingCount ?? "—"}/{s.fallingCount ?? "—"} · 多 {s.longCandidateCount}／空{" "}
                  {s.shortCandidateCount}
                </span>
                <span className="muted sm">{s.sampleNote}</span>
              </button>
              <div className="nx-sector-meta muted sm">
                Funding 中位 {s.medianFundingRate != null ? (s.medianFundingRate * 100).toFixed(4) + "%" : "—"} · OI
                5m 中位 {fmtPct(s.medianOiChange5m)} · {s.freshness}
              </div>
              <Link className="nx-link sm" to={`/crypto/sectors/${s.slug}`}>
                版塊詳情 →
              </Link>
              {open === s.id ? (
                <div className="nx-sector-members">
                  {members.length === 0 ? (
                    <p className="muted">成員載入中或暫無深度資料</p>
                  ) : (
                    <table className="nx-scanner-table compact">
                      <thead>
                        <tr>
                          <th>Symbol</th>
                          <th>24h</th>
                          <th>5m</th>
                          <th>OI 5m</th>
                          <th>方向</th>
                          <th>機會</th>
                        </tr>
                      </thead>
                      <tbody>
                        {members.slice(0, 15).map((m) => (
                          <tr key={String(m.symbol)}>
                            <td>
                              <Link to={`/market/${m.symbol}`}>{String(m.symbol).replace("USDT", "")}</Link>
                            </td>
                            <td className="mono">{fmtPct(m.change24hPct as number)}</td>
                            <td className="mono">{fmtPct(m.priceChange5mPct as number)}</td>
                            <td className="mono">{fmtPct(m.oiChange5mPct as number)}</td>
                            <td>{String(m.side || "—")}</td>
                            <td className="mono">
                              {m.opportunityScore != null ? Math.round(Number(m.opportunityScore)) : "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              ) : null}
            </li>
          ))
        )}
      </ul>
    </div>
  );
}
