import { useEffect, useRef, useState } from "react";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  ColorType,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type IPriceLine,
  type CandlestickData,
  type HistogramData,
  type Time,
} from "lightweight-charts";

const INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1d"] as const;
type Interval = (typeof INTERVALS)[number];

interface RawBar {
  time: number; // unix seconds
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

type ChartState = "loading" | "live" | "stale" | "empty" | "error";

async function fetchCandles(symbol: string, interval: string, limit: number): Promise<RawBar[]> {
  // Primary endpoint
  try {
    const r = await fetch(
      `/api/nexus/markets/${encodeURIComponent(symbol)}/candles?interval=${interval}&limit=${limit}`,
      { signal: AbortSignal.timeout(8000) },
    );
    if (r.ok) {
      const data = (await r.json()) as { bars?: RawBar[]; candles?: RawBar[]; ok?: boolean };
      const bars = data.bars ?? data.candles ?? [];
      if (bars.length > 0) return bars;
    }
  } catch {
    // fall through to fallback
  }

  // Fallback endpoint
  try {
    const r2 = await fetch(
      `/api/market/charts/ohlcv?symbol=${encodeURIComponent(symbol)}&interval=${interval}&limit=${limit}`,
      { signal: AbortSignal.timeout(8000) },
    );
    if (r2.ok) {
      const data2 = (await r2.json()) as { bars?: RawBar[] };
      return data2.bars ?? [];
    }
  } catch {
    // both failed
  }

  return [];
}

function mergeBars(existing: RawBar[], incoming: RawBar[]): RawBar[] {
  if (existing.length === 0) return incoming;
  const map = new Map<number, RawBar>(existing.map((b) => [b.time, b]));
  for (const b of incoming) map.set(b.time, b);
  return Array.from(map.values()).sort((a, b) => a.time - b.time);
}

const CHART_BG = "#0b0e14";
const TEXT_COLOR = "rgba(196,210,222,0.75)";
const GRID_COLOR = "rgba(255,255,255,0.055)";
const BORDER_COLOR = "rgba(255,255,255,0.12)";
const UP_COLOR = "#34d399";
const DOWN_COLOR = "#f87171";
const VOL_UP = "rgba(52,211,153,0.28)";
const VOL_DOWN = "rgba(248,113,113,0.28)";

/**
 * Phase 6.4 — TradingView-style candlestick+volume chart using lightweight-charts.
 * Data sourced from NEXUS API (Bybit public) — not TradingView market data.
 */
export function NexusLiveCandleChart({
  symbol,
  advanced = false,
}: {
  symbol: string;
  advanced?: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const priceLineRef = useRef<IPriceLine | null>(null);
  const barsRef = useRef<RawBar[]>([]);
  const symbolRef = useRef(symbol);
  const intervalRef = useRef<Interval>("5m");
  const lastUpdateRef = useRef<number | null>(null);

  const [interval, setIntervalState] = useState<Interval>("5m");
  const [chartState, setChartState] = useState<ChartState>("loading");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [lastPrice, setLastPrice] = useState<number | null>(null);

  // Keep refs in sync
  useEffect(() => { symbolRef.current = symbol; }, [symbol]);
  useEffect(() => { intervalRef.current = interval; }, [interval]);

  // Initialize chart once
  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;

    const chart = createChart(el, {
      width: el.clientWidth || 600,
      height: 320,
      layout: {
        background: { type: ColorType.Solid, color: CHART_BG },
        textColor: TEXT_COLOR,
        fontSize: 11,
        fontFamily: "'Inter', 'JetBrains Mono', monospace",
      },
      grid: {
        vertLines: { color: GRID_COLOR },
        horzLines: { color: GRID_COLOR },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: {
        borderColor: BORDER_COLOR,
        textColor: TEXT_COLOR,
      },
      timeScale: {
        borderColor: BORDER_COLOR,
        timeVisible: true,
        secondsVisible: false,
      },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: UP_COLOR,
      downColor: DOWN_COLOR,
      borderUpColor: UP_COLOR,
      borderDownColor: DOWN_COLOR,
      wickUpColor: UP_COLOR,
      wickDownColor: DOWN_COLOR,
    });

    const volSeries = chart.addSeries(HistogramSeries, {
      color: "rgba(100,120,160,0.3)",
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
    });

    chart.priceScale("vol").applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
      borderVisible: false,
    });

    chartRef.current = chart;
    candleRef.current = candleSeries;
    volRef.current = volSeries;

    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        chart.applyOptions({ width: entry.contentRect.width });
      }
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      try { chart.remove(); } catch { /* ignore */ }
      chartRef.current = null;
      candleRef.current = null;
      volRef.current = null;
      priceLineRef.current = null;
    };
  }, []);

  // Core data load — no changing dependencies to avoid loop
  const loadDataRef = useRef<() => Promise<void>>();
  loadDataRef.current = async () => {
    try {
      const raw = await fetchCandles(symbolRef.current, intervalRef.current, 200);

      if (raw.length === 0) {
        setChartState("empty");
        return;
      }

      const merged = mergeBars(barsRef.current, raw);
      barsRef.current = merged;

      const candleData: CandlestickData<Time>[] = merged.map((b) => ({
        time: b.time as Time,
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      }));
      const volData: HistogramData<Time>[] = merged.map((b) => ({
        time: b.time as Time,
        value: b.volume ?? 0,
        color: b.close >= b.open ? VOL_UP : VOL_DOWN,
      }));

      candleRef.current?.setData(candleData);
      volRef.current?.setData(volData);

      const last = merged[merged.length - 1];
      if (last && candleRef.current) {
        setLastPrice(last.close);
        if (priceLineRef.current) {
          priceLineRef.current.applyOptions({ price: last.close });
        } else {
          priceLineRef.current = candleRef.current.createPriceLine({
            price: last.close,
            color: "rgba(190,200,255,0.6)",
            lineWidth: 1,
            lineStyle: 2, // dashed
            axisLabelVisible: true,
            title: "",
          });
        }
      }

      const now = Date.now();
      const prev = lastUpdateRef.current;
      const stale = prev != null && now - prev > 90_000;
      lastUpdateRef.current = now;
      setChartState(stale ? "stale" : "live");
      setErrorMsg(null);
    } catch (e) {
      setChartState("error");
      setErrorMsg(e instanceof Error ? e.message : "fetch_failed");
    }
  };

  // Reload when symbol or interval changes
  useEffect(() => {
    barsRef.current = [];
    setChartState("loading");
    setLastPrice(null);
    setErrorMsg(null);
    lastUpdateRef.current = null;
    priceLineRef.current = null;
    candleRef.current?.setData([]);
    volRef.current?.setData([]);

    void loadDataRef.current?.();
    const id = window.setInterval(() => void loadDataRef.current?.(), 18_000);
    return () => window.clearInterval(id);
  }, [symbol, interval]);

  const STATE_LABEL: Record<ChartState, string> = {
    loading: "LOADING…",
    live: "LIVE",
    stale: "STALE",
    empty: "NO DATA",
    error: "ERROR",
  };

  const priceFmt = (p: number) =>
    p >= 1000 ? p.toFixed(2) : p >= 1 ? p.toFixed(4) : p.toPrecision(5);

  return (
    <div className="nx-lc-wrap">
      <div className="nx-chart-toolbar">
        {INTERVALS.map((iv) => (
          <button
            key={iv}
            type="button"
            className={interval === iv ? "active" : ""}
            onClick={() => setIntervalState(iv)}
          >
            {iv}
          </button>
        ))}
        <span className={`nx-lc-state nx-lc-state-${chartState}`}>{STATE_LABEL[chartState]}</span>
        {lastPrice != null ? (
          <span className="mono nx-lc-price">{priceFmt(lastPrice)}</span>
        ) : null}
        <span className="muted sm">Bybit via NEXUS · 非 TradingView 行情來源</span>
      </div>

      {(chartState === "empty" || chartState === "error") && (
        <div className="nx-lc-placeholder">
          {chartState === "error"
            ? <p className="muted">圖表暫不可用：{errorMsg}</p>
            : <p className="muted">K 線資料累積中 · 請稍候</p>}
        </div>
      )}

      <div
        ref={containerRef}
        className="nx-lc-canvas"
        style={{
          visibility: chartState === "loading" || chartState === "live" || chartState === "stale"
            ? "visible"
            : "hidden",
          height:
            chartState === "loading" || chartState === "live" || chartState === "stale"
              ? undefined
              : 0,
        }}
      />

      {advanced && (
        <p className="muted sm nx-lc-footer">
          bars: {barsRef.current.length} · {interval} · {symbol}
        </p>
      )}
    </div>
  );
}
