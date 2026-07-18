import { useEffect, useState } from "react";
import { getBars, getOpenInterest, type OhlcvBar, type OiPoint } from "../market/charts/nexusChartDatafeed";

const INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1d"] as const;

/**
 * NEXUS-owned chart (SVG). Data from Bybit public via NEXUS API — not TradingView market data.
 */
export function NexusOhlcvChart({
  symbol,
  advanced = false,
}: {
  symbol: string;
  advanced?: boolean;
}) {
  const [interval, setInterval] = useState<(typeof INTERVALS)[number]>("5m");
  const [bars, setBars] = useState<OhlcvBar[]>([]);
  const [oi, setOi] = useState<OiPoint[]>([]);
  const [fresh, setFresh] = useState("COLLECTING");
  const [error, setError] = useState<string | null>(null);
  const [showOi, setShowOi] = useState(advanced);

  useEffect(() => {
    let alive = true;
    const ctrl = new AbortController();
    const load = async () => {
      try {
        const body = await getBars(symbol, interval, 120);
        if (!alive) return;
        if (!body.ok) {
          setError(body.error || "chart_unavailable");
          setBars([]);
          setFresh("COLLECTING");
        } else {
          setError(null);
          setBars(body.bars || []);
          setFresh(body.freshness || "LIVE");
        }
        if (showOi) {
          const oiBody = await getOpenInterest(symbol, interval === "1m" ? "5m" : interval, 80);
          if (alive && oiBody.ok) setOi(oiBody.points || []);
        } else if (alive) setOi([]);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "chart_failed");
      }
    };
    void load();
    const id = window.setInterval(() => void load(), 30000);
    return () => {
      alive = false;
      ctrl.abort();
      window.clearInterval(id);
    };
  }, [symbol, interval, showOi]);

  const w = 640;
  const h = 220;
  const pad = 12;
  if (bars.length < 2) {
    return (
      <div className="nx-chart-card">
        <div className="nx-chart-toolbar">
          {INTERVALS.map((iv) => (
            <button key={iv} type="button" className={interval === iv ? "active" : ""} onClick={() => setInterval(iv)}>
              {iv}
            </button>
          ))}
        </div>
        <p className="muted">{error ? `圖表暫不可用：${error}` : "K 線資料累積中…"}</p>
      </div>
    );
  }

  const closes = bars.map((b) => b.close);
  const min = Math.min(...bars.map((b) => b.low));
  const max = Math.max(...bars.map((b) => b.high));
  const span = Math.max(1e-9, max - min);
  const n = bars.length;
  const candleW = Math.max(2, (w - pad * 2) / n - 1);

  const y = (price: number) => pad + (1 - (price - min) / span) * (h - pad * 2);

  let oiPath = "";
  if (oi.length > 1 && showOi) {
    const oMin = Math.min(...oi.map((p) => p.openInterest));
    const oMax = Math.max(...oi.map((p) => p.openInterest));
    const oSpan = Math.max(1e-9, oMax - oMin);
    oiPath = oi
      .map((p, i) => {
        const x = pad + (i / (oi.length - 1)) * (w - pad * 2);
        const yy = pad + (1 - (p.openInterest - oMin) / oSpan) * (h - pad * 2);
        return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${yy.toFixed(1)}`;
      })
      .join(" ");
  }

  return (
    <div className="nx-chart-card nx-ohlcv">
      <div className="nx-chart-toolbar">
        {INTERVALS.map((iv) => (
          <button key={iv} type="button" className={interval === iv ? "active" : ""} onClick={() => setInterval(iv)}>
            {iv}
          </button>
        ))}
        <label className="nx-chart-toggle">
          <input type="checkbox" checked={showOi} onChange={(e) => setShowOi(e.target.checked)} />
          持倉層
        </label>
        <span className="muted sm">{fresh} · Bybit Public via NEXUS</span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} role="img" aria-label={`${symbol} ohlcv`}>
        {bars.map((b, i) => {
          const x = pad + (i / (n - 1)) * (w - pad * 2);
          const up = b.close >= b.open;
          return (
            <g key={b.time}>
              <line x1={x} x2={x} y1={y(b.high)} y2={y(b.low)} stroke={up ? "var(--nx-long)" : "var(--nx-short)"} strokeWidth="1" />
              <rect
                x={x - candleW / 2}
                y={y(Math.max(b.open, b.close))}
                width={candleW}
                height={Math.max(1, Math.abs(y(b.open) - y(b.close)))}
                fill={up ? "var(--nx-long)" : "var(--nx-short)"}
              />
            </g>
          );
        })}
        {oiPath ? (
          <path d={oiPath} fill="none" stroke="var(--nx-accent)" strokeWidth="1.5" strokeDasharray="4 3" />
        ) : null}
      </svg>
      <p className="muted sm">
        最新收盤 {closes[closes.length - 1]?.toFixed?.(4) ?? "—"} · bars {bars.length} · 非 TradingView 行情來源
      </p>
    </div>
  );
}
