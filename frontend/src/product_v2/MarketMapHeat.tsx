import { Link } from "react-router-dom";
import { useMemo, type CSSProperties } from "react";
import type { LiveRankingRow } from "../market/liveMarketRanking";
import { MetricSpark } from "./MetricSpark";
import { TokenIcon } from "./TokenIcon";

type MapMetric = "change_24h" | "activity" | "oi" | "funding" | "risk" | "nex_rank";

const METRICS: { id: MapMetric; label: string }[] = [
  { id: "change_24h", label: "24h" },
  { id: "activity", label: "Activity" },
  { id: "oi", label: "OI" },
  { id: "funding", label: "Funding" },
  { id: "risk", label: "Risk" },
  { id: "nex_rank", label: "NEX Rank" },
];

function metricValue(r: LiveRankingRow, m: MapMetric): number | null {
  switch (m) {
    case "change_24h":
      return r.change_24h ?? null;
    case "activity":
      return r.activity_metric ?? null;
    case "oi":
      return r.oi_change ?? null;
    case "funding":
      return r.funding_rate != null ? r.funding_rate * 100 : null;
    case "risk":
      return r.risk_score ?? null;
    case "nex_rank":
      return r.rank_score ?? null;
    default:
      return null;
  }
}

function fmtCell(m: MapMetric, v: number | null): string {
  if (v == null || Number.isNaN(v)) return "—";
  if (m === "funding") return `${v >= 0 ? "+" : ""}${v.toFixed(3)}%`;
  if (m === "change_24h" || m === "oi") return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
  if (m === "nex_rank" || m === "risk" || m === "activity") return String(Math.round(v));
  return String(v);
}

/**
 * Market Map — grid heatmap sized by real volume when available; else equal cells.
 * No fabricated treemap sizes.
 */
export function MarketMapHeat({
  rows,
  metric,
  onMetricChange,
  seriesBySymbol,
}: {
  rows: LiveRankingRow[];
  metric: MapMetric;
  onMetricChange: (m: MapMetric) => void;
  seriesBySymbol?: Record<string, { points?: { timestamp: number; value: number }[] } | undefined>;
}) {
  const sized = useMemo(() => {
    const pool = rows.slice(0, 24);
    const vols = pool.map((r) => (r.volume_24h != null && r.volume_24h > 0 ? r.volume_24h : null));
    const truthy = vols.filter((v): v is number => v != null);
    const canSize = truthy.length >= Math.max(4, Math.floor(pool.length * 0.5));
    return { pool, canSize, mode: canSize ? "volume_heatmap" : "grid_heatmap" as const };
  }, [rows]);

  const values = sized.pool.map((r) => metricValue(r, metric));
  const finite = values.filter((v): v is number => v != null && Number.isFinite(v));
  const maxAbs = Math.max(1e-9, ...finite.map((v) => Math.abs(v)));

  if (!sized.pool.length) {
    return (
      <div className="mp2-market-map" data-testid="market-map">
        <p className="mp2-nodata">NO DATA</p>
      </div>
    );
  }

  return (
    <div className="mp2-market-map" data-testid="market-map" data-map-mode={sized.mode}>
      <div className="mp2-map-metric-row" role="tablist" aria-label="Market Map metric">
        {METRICS.map((m) => (
          <button
            key={m.id}
            type="button"
            className={metric === m.id ? "active" : undefined}
            onClick={() => onMetricChange(m.id)}
          >
            {m.label}
          </button>
        ))}
      </div>
      <div className={`mp2-map-grid${sized.canSize ? " sized" : ""}`}>
        {sized.pool.map((r, i) => {
          const v = values[i];
          const intensity = v == null ? 0 : Math.min(1, Math.abs(v) / maxAbs);
          const pos = (v ?? 0) >= 0;
          const vol = r.volume_24h != null && r.volume_24h > 0 ? r.volume_24h : 1;
          const flex = sized.canSize ? Math.max(0.6, Math.sqrt(vol)) : 1;
          const sparkPts = seriesBySymbol?.[r.symbol]?.points;
          return (
            <Link
              key={r.candidate_id}
              to={`/market/${r.symbol}`}
              className={`mp2-map-cell${v == null ? " empty" : pos ? " pos" : " neg"}`}
              style={
                {
                  flexGrow: flex,
                  ["--mp2-heat" as string]: String(0.12 + intensity * 0.55),
                } as CSSProperties
              }
            >
              <span className="mp2-sym-with-icon">
                <TokenIcon symbol={r.symbol} size={14} />
                <span className="mono">{r.symbol.replace("USDT", "")}</span>
              </span>
              <span className="mono val">{fmtCell(metric, v)}</span>
              {metric === "change_24h" && sparkPts && sparkPts.length >= 2 ? (
                <MetricSpark points={sparkPts} width={40} height={14} positive={pos} />
              ) : null}
            </Link>
          );
        })}
      </div>
      <p className="muted" style={{ fontSize: "0.6875rem", marginTop: 6 }}>
        {sized.canSize ? "體積加權熱力（真實 24h volume）" : "等格熱力（volume 覆蓋不足，不虛構尺寸）"}
      </p>
    </div>
  );
}

export type { MapMetric };
