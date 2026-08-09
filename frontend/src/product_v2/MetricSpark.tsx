/** Compact SVG spark from true market series (timestamps + gap breaks). No invented candles. */

export type SparkTimedPoint = { timestamp: number; value: number };

function finiteValues(values: Array<number | null | undefined>): number[] {
  return values.filter((v): v is number => v != null && Number.isFinite(v));
}

/**
 * Render spark from equal-index values (legacy) OR timestamped closes with gap detection.
 * Gaps (>1.5× expected interval) break the path; never invent equal-space ticks.
 */
export function MetricSpark({
  values,
  points,
  expectedIntervalMs,
  width = 64,
  height = 22,
  positive,
}: {
  values?: Array<number | null | undefined>;
  points?: SparkTimedPoint[];
  expectedIntervalMs?: number;
  width?: number;
  height?: number;
  positive?: boolean | null;
}) {
  const timed =
    points && points.length
      ? points.filter((p) => Number.isFinite(p.timestamp) && Number.isFinite(p.value))
      : null;

  if (timed && timed.length < 2) {
    return (
      <span className="mp2-spark mp2-spark-empty" aria-label="NO DATA" style={{ width, height }} title="NO DATA" />
    );
  }

  const pts = timed ? timed.map((p) => p.value) : finiteValues(values || []);
  if (pts.length < 2) {
    return (
      <span className="mp2-spark mp2-spark-empty" aria-label="NO DATA" style={{ width, height }} title="NO DATA" />
    );
  }

  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const span = max - min || 1;
  const t0 = timed ? timed[0].timestamp : 0;
  const t1 = timed ? timed[timed.length - 1].timestamp : 1;
  const tSpan = Math.max(1, t1 - t0);
  const gapMs = (expectedIntervalMs || 0) * 1.5;

  const segments: string[] = [];
  let current: string[] = [];
  for (let i = 0; i < pts.length; i++) {
    const x = timed
      ? ((timed[i].timestamp - t0) / tSpan) * (width - 2) + 1
      : (i / (pts.length - 1)) * (width - 2) + 1;
    const y = height - 2 - ((pts[i] - min) / span) * (height - 4);
    if (timed && i > 0 && gapMs > 0 && timed[i].timestamp - timed[i - 1].timestamp > gapMs) {
      if (current.length >= 2) segments.push(current.join(" "));
      current = [];
    }
    current.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  }
  if (current.length >= 2) segments.push(current.join(" "));
  if (!segments.length) {
    return (
      <span className="mp2-spark mp2-spark-empty" aria-label="NO DATA" style={{ width, height }} title="NO DATA" />
    );
  }

  const last = pts[pts.length - 1];
  const first = pts[0];
  const up = positive != null ? positive : last >= first;
  return (
    <svg
      className={`mp2-spark${up ? " pos" : " neg"}`}
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      aria-hidden
      data-spark-mode={timed ? "timestamped" : "index"}
      data-spark-segments={segments.length}
    >
      {segments.map((d, i) => (
        <polyline key={i} fill="none" stroke="currentColor" strokeWidth="1.5" points={d} />
      ))}
    </svg>
  );
}

/** Step spark for SERVER rank history (lower rank = better → invert Y). */
export function RankStepSpark({
  points,
  width = 48,
  height = 18,
}: {
  points: SparkTimedPoint[];
  width?: number;
  height?: number;
}) {
  const timed = points.filter((p) => Number.isFinite(p.timestamp) && Number.isFinite(p.value));
  if (timed.length < 2) {
    return <span className="mp2-spark mp2-spark-empty" style={{ width, height }} title="NO DATA" aria-label="NO DATA" />;
  }
  const vals = timed.map((p) => p.value);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;
  const t0 = timed[0].timestamp;
  const tSpan = Math.max(1, timed[timed.length - 1].timestamp - t0);
  const coords: string[] = [];
  for (let i = 0; i < timed.length; i++) {
    const x = ((timed[i].timestamp - t0) / tSpan) * (width - 2) + 1;
    // Invert: rank 1 near top
    const y = 2 + ((timed[i].value - min) / span) * (height - 4);
    if (i > 0) {
      const px = ((timed[i - 1].timestamp - t0) / tSpan) * (width - 2) + 1;
      const py = 2 + ((timed[i - 1].value - min) / span) * (height - 4);
      coords.push(`${px.toFixed(1)},${py.toFixed(1)}`);
      coords.push(`${x.toFixed(1)},${py.toFixed(1)}`);
    }
    coords.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  }
  const improved = timed[timed.length - 1].value < timed[0].value;
  return (
    <svg
      className={`mp2-spark mp2-rank-step${improved ? " pos" : " neg"}`}
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      aria-hidden
      data-spark-mode="rank-step"
    >
      <polyline fill="none" stroke="currentColor" strokeWidth="1.4" points={coords.join(" ")} />
    </svg>
  );
}

export function ActivityBar({ value, max = 40 }: { value: number | null | undefined; max?: number }) {
  if (value == null || !Number.isFinite(value)) {
    return (
      <span className="mp2-activity-bar empty" title="NO DATA" aria-label="NO DATA">
        <span style={{ width: "0%" }} />
      </span>
    );
  }
  const v = Math.max(0, Math.min(max, value));
  const pct = Math.round((v / max) * 100);
  return (
    <span className="mp2-activity-bar" title={String(value)} aria-hidden>
      <span style={{ width: `${pct}%` }} />
    </span>
  );
}

export function RiskBar({ value, max = 100 }: { value: number | null | undefined; max?: number }) {
  if (value == null || !Number.isFinite(value)) {
    return <span className="mp2-risk-bar empty" title="NO DATA" aria-label="NO DATA" />;
  }
  const pct = Math.round((Math.max(0, Math.min(max, value)) / max) * 100);
  const tone = pct >= 70 ? "hi" : pct >= 40 ? "mid" : "lo";
  return (
    <span className={`mp2-risk-bar ${tone}`} title={String(Math.round(value))} aria-hidden>
      <span style={{ width: `${pct}%` }} />
    </span>
  );
}

/** Semantic funding scale: short ← ● → long (exchange density, not neon). */
export function FundingScale({
  rate,
}: {
  rate: number | null | undefined;
}) {
  if (rate == null || !Number.isFinite(rate)) {
    return <span className="mp2-fund-scale empty" title="NO DATA">—</span>;
  }
  // Typical perp funding ~±0.01% → ±0.0001 decimal; clamp visual to ±0.05%
  const pct = rate * 100;
  const clamped = Math.max(-0.05, Math.min(0.05, pct));
  const pos = ((clamped + 0.05) / 0.1) * 100;
  return (
    <span
      className={`mp2-fund-scale${pct > 0.001 ? " long" : pct < -0.001 ? " short" : ""}`}
      title={`${pct >= 0 ? "+" : ""}${pct.toFixed(4)}%`}
      aria-hidden
    >
      <span className="track" />
      <span className="knob" style={{ left: `${pos}%` }} />
    </span>
  );
}

export function OiDirection({ change }: { change: number | null | undefined }) {
  if (change == null || !Number.isFinite(change)) {
    return <span className="mp2-oi-dir muted" title="NO DATA">—</span>;
  }
  if (change > 0.05) return <span className="mp2-oi-dir pos" title={`+${change.toFixed(2)}%`}>▲</span>;
  if (change < -0.05) return <span className="mp2-oi-dir neg" title={`${change.toFixed(2)}%`}>▼</span>;
  return <span className="mp2-oi-dir flat" title={`${change.toFixed(2)}%`}>●</span>;
}

export function RankArrow({ event, delta }: { event: string; delta: number | null | undefined }) {
  if (event === "NEW") return <span className="mp2-rank-arrow new">NEW</span>;
  if (event === "OUT") return <span className="mp2-rank-arrow out">OUT</span>;
  if (event === "UP") return <span className="mp2-rank-arrow up">↑{delta != null && delta !== 0 ? delta : ""}</span>;
  if (event === "DOWN")
    return (
      <span className="mp2-rank-arrow down">↓{delta != null && delta !== 0 ? Math.abs(delta) : ""}</span>
    );
  return <span className="mp2-rank-arrow flat">·</span>;
}

/** Horizontal pipeline bars — Scanner → Radar → Trade → Qualified. */
export function PipelineBars({
  stages,
}: {
  stages: { key: string; label: string; value: number | null | undefined }[];
}) {
  const nums = stages.map((s) => (s.value != null && Number.isFinite(s.value) ? s.value : null));
  const max = Math.max(1, ...nums.filter((n): n is number => n != null));
  return (
    <div className="mp2-pipeline" data-testid="opportunity-pipeline">
      {stages.map((s, i) => {
        const v = nums[i];
        const pct = v == null ? 0 : Math.round((v / max) * 100);
        return (
          <div key={s.key} className="mp2-pipeline-stage">
            <div className="mp2-pipeline-bar-track">
              {v == null ? (
                <span className="mp2-nodata">NO DATA</span>
              ) : (
                <span className="mp2-pipeline-bar" style={{ width: `${Math.max(4, pct)}%` }} />
              )}
            </div>
            <div className="mp2-pipeline-meta">
              <span className="lbl">{s.label}</span>
              <span className="mono">{v == null ? "—" : v}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** Market risk gauge: LOW ← ● → HIGH from real high-risk count / universe. */
export function RiskGauge({
  highRisk,
  universe,
}: {
  highRisk: number | null | undefined;
  universe: number | null | undefined;
}) {
  if (highRisk == null || !Number.isFinite(highRisk)) {
    return (
      <div className="mp2-risk-gauge" data-testid="market-risk-gauge">
        <span className="mp2-nodata">NO DATA</span>
      </div>
    );
  }
  const uni = universe != null && universe > 0 ? universe : 100;
  const ratio = Math.max(0, Math.min(1, highRisk / Math.max(uni * 0.25, 1)));
  const label = ratio < 0.33 ? "LOW" : ratio < 0.66 ? "MID" : "HIGH";
  return (
    <div className={`mp2-risk-gauge tone-${label.toLowerCase()}`} data-testid="market-risk-gauge">
      <div className="mp2-risk-track">
        <span className="end">LOW</span>
        <span className="rail">
          <span className="knob" style={{ left: `${ratio * 100}%` }} />
        </span>
        <span className="end">HIGH</span>
      </div>
      <div className="mp2-risk-readout mono">
        {label} · {highRisk}
      </div>
    </div>
  );
}
