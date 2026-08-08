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

export function ActivityBar({ value, max = 40 }: { value: number | null | undefined; max?: number }) {
  const v = value == null || !Number.isFinite(value) ? 0 : Math.max(0, Math.min(max, value));
  const pct = Math.round((v / max) * 100);
  return (
    <span className="mp2-activity-bar" title={value == null ? "—" : String(value)} aria-hidden>
      <span style={{ width: `${pct}%` }} />
    </span>
  );
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
