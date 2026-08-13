export function SparkChart({ values }: { values: number[] }) {
  if (!values.length) return <div className="mpv1-spark" />;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const w = 320;
  const h = 120;
  const pad = 8;
  const span = max - min || 1;
  const pts = values
    .map((v, i) => {
      const x = pad + (i / (values.length - 1)) * (w - pad * 2);
      const y = h - pad - ((v - min) / span) * (h - pad * 2);
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <svg className="mpv1-spark" viewBox={`0 0 ${w} ${h}`} role="img" aria-label="價格走勢示意">
      <polyline fill="none" stroke="#1d4ed8" strokeWidth="2.5" points={pts} />
    </svg>
  );
}
