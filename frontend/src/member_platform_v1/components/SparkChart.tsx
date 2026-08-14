import type { ReactNode } from "react";

export function SparkChart({
  values,
  compact,
  tone = "accent",
}: {
  values: number[];
  compact?: boolean;
  tone?: "accent" | "bull" | "bear";
}) {
  if (!values.length) return <div className={compact ? "mpv1-sparkline" : "mpv1-spark"} />;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const w = compact ? 72 : 640;
  const h = compact ? 28 : 160;
  const pad = compact ? 2 : 8;
  const span = max - min || 1;
  const pts = values
    .map((v, i) => {
      const x = pad + (i / Math.max(values.length - 1, 1)) * (w - pad * 2);
      const y = h - pad - ((v - min) / span) * (h - pad * 2);
      return `${x},${y}`;
    })
    .join(" ");
  const area = `${pad},${h - pad} ${pts} ${w - pad},${h - pad}`;
  const stroke = tone === "bull" ? "#059669" : tone === "bear" ? "#dc2626" : "#2563eb";
  const fill = tone === "bull" ? "rgba(5,150,105,0.12)" : tone === "bear" ? "rgba(220,38,38,0.1)" : "rgba(37,99,235,0.12)";
  return (
    <svg
      className={compact ? "mpv1-sparkline" : "mpv1-spark"}
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      role="img"
      aria-label="走勢示意"
    >
      {!compact ? <polygon fill={fill} points={area} /> : null}
      <polyline fill="none" stroke={stroke} strokeWidth={compact ? 2 : 2.4} points={pts} />
    </svg>
  );
}

type Candle = { o: number; h: number; l: number; c: number; v?: number };

export function CandleChart({ candles }: { candles: Candle[] }) {
  if (!candles.length) return <div className="mpv1-candle-wrap" />;

  const w = 900;
  const h = 320;
  const padL = 8;
  const padR = 56;
  const padT = 16;
  const volH = 48;
  const chartH = h - padT - volH - 22;
  const highs = candles.map((c) => c.h);
  const lows = candles.map((c) => c.l);
  const min = Math.min(...lows);
  const max = Math.max(...highs);
  const span = max - min || 1;
  const plotW = w - padL - padR;
  const slot = plotW / candles.length;
  const y = (v: number) => padT + ((max - v) / span) * chartH;
  const last = candles[candles.length - 1];
  const vols = candles.map((c, i) => c.v ?? Math.abs(c.c - c.o) * (800 + (i % 7) * 120));
  const vmax = Math.max(...vols) || 1;
  const gridYs = [0.15, 0.4, 0.65, 0.9].map((p) => padT + chartH * p);
  const priceLabels = [max, min + span * 0.66, min + span * 0.33, min];

  return (
    <svg className="mpv1-candle-svg" viewBox={`0 0 ${w} ${h}`} role="img" aria-label="K 線示意">
      {gridYs.map((gy, i) => (
        <g key={i}>
          <line x1={padL} x2={w - padR} y1={gy} y2={gy} stroke="#e2e8f0" strokeWidth="1" strokeDasharray="3 4" />
          <text x={w - padR + 6} y={gy + 3} fontSize="10" fill="#94a3b8">
            {priceLabels[i].toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </text>
        </g>
      ))}
      {candles.map((c, i) => {
        const x = padL + i * slot + slot / 2;
        const up = c.c >= c.o;
        const color = up ? "#059669" : "#dc2626";
        const bodyTop = y(Math.max(c.o, c.c));
        const bodyBot = y(Math.min(c.o, c.c));
        const bodyH = Math.max(1.5, bodyBot - bodyTop);
        const vh = (vols[i] / vmax) * (volH - 6);
        return (
          <g key={i}>
            <line x1={x} x2={x} y1={y(c.h)} y2={y(c.l)} stroke={color} strokeWidth="1.1" />
            <rect
              x={x - Math.max(1.2, slot * 0.32)}
              y={bodyTop}
              width={Math.max(2.4, slot * 0.64)}
              height={bodyH}
              fill={color}
              rx="0.4"
            />
            <rect
              x={x - Math.max(1, slot * 0.28)}
              y={h - 18 - vh}
              width={Math.max(2, slot * 0.55)}
              height={vh}
              fill={up ? "rgba(5,150,105,0.35)" : "rgba(220,38,38,0.3)"}
            />
          </g>
        );
      })}
      <line
        x1={padL}
        x2={w - padR}
        y1={y(last.c)}
        y2={y(last.c)}
        stroke="#2563eb"
        strokeWidth="1"
        strokeDasharray="4 3"
      />
      <rect x={w - padR + 2} y={y(last.c) - 8} width={50} height={16} rx="3" fill="#2563eb" />
      <text x={w - padR + 27} y={y(last.c) + 3.5} textAnchor="middle" fontSize="10" fontWeight="700" fill="#fff">
        {last.c.toLocaleString(undefined, { maximumFractionDigits: 0 })}
      </text>
      {["09:00", "12:00", "15:00", "18:00"].map((t, i) => (
        <text key={t} x={padL + (plotW * (i + 0.5)) / 4} y={h - 4} fontSize="10" fill="#94a3b8" textAnchor="middle">
          {t}
        </text>
      ))}
    </svg>
  );
}

const INTERVALS = ["1m", "5m", "15m", "1H", "4H", "1D"] as const;

export function ChartToolbar({
  interval,
  onInterval,
}: {
  interval: string;
  onInterval: (v: string) => void;
}) {
  const tools: Array<{ title: string; icon: ReactNode }> = [
    {
      title: "趨勢線",
      icon: (
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
          <path d="M2 11 L12 3" stroke="currentColor" strokeWidth="1.6" fill="none" />
          <circle cx="2" cy="11" r="1.4" fill="currentColor" />
          <circle cx="12" cy="3" r="1.4" fill="currentColor" />
        </svg>
      ),
    },
    {
      title: "水平線",
      icon: (
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
          <path d="M2 7 H12" stroke="currentColor" strokeWidth="1.6" />
        </svg>
      ),
    },
    {
      title: "矩形",
      icon: (
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
          <rect x="2.5" y="3.5" width="9" height="7" rx="1" stroke="currentColor" strokeWidth="1.4" fill="none" />
        </svg>
      ),
    },
    {
      title: "指標",
      icon: <span style={{ fontSize: 11, fontWeight: 700 }}>fx</span>,
    },
    {
      title: "圖表樣式",
      icon: (
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
          <path d="M3 11 V6 M7 11 V3 M11 11 V8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      ),
    },
    {
      title: "截圖",
      icon: (
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
          <rect x="2" y="3.5" width="10" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.3" fill="none" />
          <circle cx="7" cy="7.5" r="2" stroke="currentColor" strokeWidth="1.2" fill="none" />
        </svg>
      ),
    },
    {
      title: "全螢幕",
      icon: (
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
          <path
            d="M3 5.5V3h2.5M8.5 3H11v2.5M11 8.5V11H8.5M5.5 11H3V8.5"
            stroke="currentColor"
            strokeWidth="1.3"
            fill="none"
            strokeLinecap="round"
          />
        </svg>
      ),
    },
  ];

  return (
    <div className="mpv1-chart-toolbar">
      <div className="mpv1-chart-intervals">
        {INTERVALS.map((t) => (
          <button
            key={t}
            type="button"
            className={`mpv1-chart-iv${interval === t ? " is-on" : ""}`}
            onClick={() => onInterval(t)}
          >
            {t}
          </button>
        ))}
      </div>
      <div className="mpv1-chart-tools" aria-label="圖表工具（示意）">
        {tools.map((t) => (
          <button key={t.title} type="button" className="mpv1-chart-tool" title={t.title}>
            {t.icon}
          </button>
        ))}
      </div>
    </div>
  );
}
