/** Shared visual primitives for reference-match UI */

export function ScoreRing({
  score,
  size = 40,
}: {
  score: number | null;
  size?: number;
}) {
  if (score == null) return <span className="mpv1-score">—</span>;
  const r = (size - 6) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score)) / 100;
  const color = score >= 70 ? "#059669" : score >= 50 ? "#2563eb" : "#d97706";
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="mpv1-score-ring" aria-label={`評分 ${score}`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e2e8f0" strokeWidth="3" />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth="3"
        strokeLinecap="round"
        strokeDasharray={`${c * pct} ${c}`}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle" fontSize={size * 0.32} fontWeight="700" fill="#0f172a">
        {score}
      </text>
    </svg>
  );
}

export function DonutChart({
  segments,
  centerLabel,
  centerSub,
  size = 120,
}: {
  segments: Array<{ value: number; color: string }>;
  centerLabel: string;
  centerSub?: string;
  size?: number;
}) {
  const total = segments.reduce((s, x) => s + x.value, 0) || 1;
  const r = size * 0.36;
  const stroke = size * 0.14;
  const c = 2 * Math.PI * r;
  let offset = 0;
  return (
    <div className="mpv1-donut-wrap" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {segments.map((seg, i) => {
          const len = (seg.value / total) * c;
          const el = (
            <circle
              key={i}
              cx={size / 2}
              cy={size / 2}
              r={r}
              fill="none"
              stroke={seg.color}
              strokeWidth={stroke}
              strokeDasharray={`${len} ${c - len}`}
              strokeDashoffset={-offset}
              transform={`rotate(-90 ${size / 2} ${size / 2})`}
            />
          );
          offset += len;
          return el;
        })}
      </svg>
      <div className="mpv1-donut-center">
        <strong>{centerLabel}</strong>
        {centerSub ? <span>{centerSub}</span> : null}
      </div>
    </div>
  );
}

export function BiasGauge({ position = 0.68 }: { position?: number }) {
  const pct = Math.max(0.05, Math.min(0.95, position)) * 100;
  return (
    <div className="mpv1-bias-gauge" aria-hidden>
      <div className="mpv1-bias-gauge-track" />
      <div className="mpv1-bias-gauge-needle" style={{ left: `${pct}%` }} />
    </div>
  );
}

export function ToggleSwitch({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange?: (v: boolean) => void;
  label?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label || "開關"}
      className={`mpv1-switch${checked ? " is-on" : ""}`}
      onClick={() => onChange?.(!checked)}
    >
      <span className="mpv1-switch-knob" />
    </button>
  );
}
