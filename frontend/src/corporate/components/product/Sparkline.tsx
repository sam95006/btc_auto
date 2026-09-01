/** SVG sparkline from backend OHLCV closes (/history). No fabricated points —
 * renders nothing until real data arrives. Direction colour from first→last. */
import { useEffect, useState } from "react";
import { getHistory } from "../../api/client";

export function Sparkline({ symbol, interval = "1h", limit = 48, className = "" }: {
  symbol: string; interval?: string; limit?: number; className?: string;
}) {
  const [pts, setPts] = useState<number[] | null>(null);
  useEffect(() => {
    let on = true;
    getHistory(symbol, interval, limit)
      .then((h) => { if (on) setPts(h.availability === "READY" && Array.isArray(h.points) ? h.points : []); })
      .catch(() => on && setPts([]));
    return () => { on = false; };
  }, [symbol, interval, limit]);

  if (pts === null) return <svg className={`corp-fs-spark ${className}`} viewBox="0 0 100 40" aria-hidden />;
  if (pts.length < 2) return <svg className={`corp-fs-spark ${className}`} viewBox="0 0 100 40" aria-hidden />;

  const min = Math.min(...pts), max = Math.max(...pts);
  const range = max - min || 1;
  const n = pts.length;
  const x = (i: number) => (i / (n - 1)) * 100;
  const y = (v: number) => 38 - ((v - min) / range) * 34;
  const line = pts.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(2)},${y(v).toFixed(2)}`).join(" ");
  const area = `${line} L100,40 L0,40 Z`;
  const up = pts[n - 1] >= pts[0];

  return (
    <svg className={`corp-fs-spark ${up ? "up" : "down"} ${className}`} viewBox="0 0 100 40" preserveAspectRatio="none" aria-hidden>
      <defs>
        <linearGradient id="fs-spark-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={up ? "rgba(34,201,138,0.35)" : "rgba(255,95,116,0.32)"} />
          <stop offset="100%" stopColor="rgba(5,7,14,0)" />
        </linearGradient>
      </defs>
      <path className="area" d={area} />
      <path className="line" d={line} />
    </svg>
  );
}
