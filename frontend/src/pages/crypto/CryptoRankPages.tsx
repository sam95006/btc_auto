import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { fetchScannerCharts, fetchScannerCandidates } from "../../market/scannerApi";

function fmtPct(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

export function CryptoOiPage() {
  const [rows, setRows] = useState<
    { symbol: string; oiChange5mPct?: number | null; opportunityScore?: number; side?: string; stage?: string }[]
  >([]);
  useEffect(() => {
    let alive = true;
    const load = async () => {
      const body = await fetchScannerCandidates(undefined, 40);
      if (!alive) return;
      const list = (body.candidates || [])
        .filter((c) => c.oiChange5mPct != null)
        .sort((a, b) => Math.abs(b.oiChange5mPct || 0) - Math.abs(a.oiChange5mPct || 0));
      setRows(list);
    };
    void load();
    const id = window.setInterval(() => void load(), 15000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);
  return (
    <div className="page-stack nx-p3">
      <header className="nx-ov-header">
        <h1 className="nx-page-title">OI 排行</h1>
        <p className="nx-status-line">深度掃描層 · 真實 5m 持倉變動 · Research only</p>
        <Link to="/crypto/sectors">← 版塊</Link>
      </header>
      <ul className="nx-turn-list">
        {rows.map((r) => (
          <li key={r.symbol}>
            <Link to={`/market/${r.symbol}`} className="nx-turn-row">
              <span className="mono">{r.symbol.replace("USDT", "")}</span>
              <span>OI 5m {fmtPct(r.oiChange5mPct)}</span>
              <span>{r.side}</span>
              <span className="muted">{r.stage}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function CryptoFundingPage() {
  const [rows, setRows] = useState<{ symbol: string; fundingRate?: number | null; side?: string }[]>([]);
  useEffect(() => {
    let alive = true;
    const load = async () => {
      const body = await fetchScannerCandidates(undefined, 40);
      if (!alive) return;
      const list = (body.candidates || [])
        .filter((c) => c.fundingRate != null)
        .sort((a, b) => Math.abs(b.fundingRate || 0) - Math.abs(a.fundingRate || 0));
      setRows(list);
    };
    void load();
    const id = window.setInterval(() => void load(), 15000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);
  return (
    <div className="page-stack nx-p3">
      <header className="nx-ov-header">
        <h1 className="nx-page-title">Funding 排行</h1>
        <p className="nx-status-line">
          資金費率是擁擠度參考，不等於做多／做空方向。點值來自掃描器，非歷史序列虛構。
        </p>
        <Link to="/crypto/sectors">← 版塊</Link>
      </header>
      <ul className="nx-turn-list">
        {rows.map((r) => (
          <li key={r.symbol}>
            <Link to={`/market/${r.symbol}`} className="nx-turn-row">
              <span className="mono">{r.symbol.replace("USDT", "")}</span>
              <span className="mono">
                {r.fundingRate != null ? `${(r.fundingRate * 100).toFixed(4)}%` : "—"}
              </span>
              <span className="muted">
                {r.fundingRate != null && Math.abs(r.fundingRate) > 0.0003 ? "部位偏擁擠" : "中性範圍"}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function CryptoPriceOiPage() {
  const [points, setPoints] = useState<
    { symbol: string; side: string; priceChange5mPct: number; oiChange5mPct: number; stage?: string }[]
  >([]);
  useEffect(() => {
    let alive = true;
    const load = async () => {
      const ch = await fetchScannerCharts();
      if (!alive) return;
      setPoints(ch.priceOiQuadrant || []);
    };
    void load();
    const id = window.setInterval(() => void load(), 15000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);
  return (
    <div className="page-stack nx-p3">
      <header className="nx-ov-header">
        <h1 className="nx-page-title">價格與持倉結構</h1>
        <p className="nx-status-line">僅深度掃描、具備真實 5m 窗口的標的 · Collecting 不進圖</p>
        <Link to="/crypto/sectors">← 版塊</Link>
      </header>
      <section className="nx-chart-card nx-quadrant">
        <div className="nx-quad-plot">
          {points.slice(0, 60).map((p) => (
            <Link
              key={p.symbol}
              to={`/market/${p.symbol}`}
              className={`nx-quad-dot side-${p.side.toLowerCase()}`}
              style={{
                left: `${50 + Math.max(-42, Math.min(42, p.priceChange5mPct * 6))}%`,
                bottom: `${50 + Math.max(-42, Math.min(42, p.oiChange5mPct * 6))}%`,
              }}
              title={`${p.symbol} px ${p.priceChange5mPct}% oi ${p.oiChange5mPct}%`}
            />
          ))}
          <span className="nx-quad-axis-x">5m 價格 →</span>
          <span className="nx-quad-axis-y">5m 持倉 ↑</span>
        </div>
        {points.length === 0 ? <p className="muted">資料累積中…</p> : null}
      </section>
    </div>
  );
}
