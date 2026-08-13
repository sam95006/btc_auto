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

export function CandleChart({
  candles,
}: {
  candles: Array<{ o: number; h: number; l: number; c: number }>;
}) {
  if (!candles.length) return <div className="mpv1-candle-wrap" />;
  const w = 720;
  const h = 260;
  const padX = 8;
  const padY = 12;
  const highs = candles.map((c) => c.h);
  const lows = candles.map((c) => c.l);
  const min = Math.min(...lows);
  const max = Math.max(...highs);
  const span = max - min || 1;
  const slot = (w - padX * 2) / candles.length;
  const y = (v: number) => padY + ((max - v) / span) * (h - padY * 2);

  return (
    <svg className="mpv1-spark" viewBox={`0 0 ${w} ${h}`} role="img" aria-label="K 線示意">
      {candles.map((c, i) => {
        const x = padX + i * slot + slot / 2;
        const up = c.c >= c.o;
        const color = up ? "#059669" : "#dc2626";
        const bodyTop = y(Math.max(c.o, c.c));
        const bodyBot = y(Math.min(c.o, c.c));
        const bodyH = Math.max(1.5, bodyBot - bodyTop);
        return (
          <g key={i}>
            <line x1={x} x2={x} y1={y(c.h)} y2={y(c.l)} stroke={color} strokeWidth="1.2" />
            <rect
              x={x - Math.max(1.5, slot * 0.28)}
              y={bodyTop}
              width={Math.max(3, slot * 0.56)}
              height={bodyH}
              fill={color}
              rx="0.5"
            />
          </g>
        );
      })}
    </svg>
  );
}
