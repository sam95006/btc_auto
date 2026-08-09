import { useMemo } from "react";
import type { MarketSummaryPoint } from "../market/marketSummaryHistory";
import { MetricSpark, PipelineBars, RiskGauge } from "./MetricSpark";

function regimeTone(regime: string): string {
  if (regime.includes("多") && !regime.includes("混合")) return " pos";
  if (regime.includes("空")) return " neg";
  return "";
}

/**
 * MARKET STATE VISUAL — chart-first Market Now.
 * Visual → number → label → details on demand. No fabricated history.
 */
export function MarketStateVisual({
  rising,
  falling,
  neutral,
  regime,
  highRisk,
  universe,
  scannerCount,
  radarCount,
  tradeCount,
  qualifiedCount,
  history,
  loading,
}: {
  rising: number;
  falling: number;
  neutral: number;
  regime: string;
  highRisk: number | null | undefined;
  universe: number | null | undefined;
  scannerCount: number;
  radarCount: number;
  tradeCount: number;
  qualifiedCount: number;
  history: MarketSummaryPoint[];
  loading?: boolean;
}) {
  const breadthTotal = Math.max(1, rising + falling + neutral);
  const realHistory = useMemo(
    () => history.filter((p) => p && p.fabricated !== true && Number.isFinite(p.timestamp)),
    [history],
  );

  const breadthSpark = useMemo(() => {
    if (realHistory.length < 2) return null;
    return realHistory.map((p) => ({
      timestamp: p.timestamp,
      value: p.rising - p.falling,
    }));
  }, [realHistory]);

  const regimeTimeline = useMemo(() => {
    if (realHistory.length < 2) return [];
    // Collapse consecutive same regime into segments (real only).
    const segs: { regime: string; from: number; to: number }[] = [];
    for (const p of realHistory) {
      const last = segs[segs.length - 1];
      if (last && last.regime === p.regime) {
        last.to = p.timestamp;
      } else {
        segs.push({ regime: p.regime, from: p.timestamp, to: p.timestamp });
      }
    }
    return segs;
  }, [realHistory]);

  const activitySpark = useMemo(() => {
    if (realHistory.length < 2) return null;
    return realHistory.map((p) => ({
      timestamp: p.timestamp,
      value: p.radar_eligible_count,
    }));
  }, [realHistory]);

  const activityEvents = useMemo(() => {
    if (!realHistory.length) return null;
    const last = realHistory[realHistory.length - 1];
    const sum = last.events_new + last.events_up + last.events_down + last.events_out;
    // Prefer rolling 24h sums when multiple points exist
    if (realHistory.length >= 2) {
      const n = realHistory.reduce((a, p) => a + p.events_new, 0);
      const u = realHistory.reduce((a, p) => a + p.events_up, 0);
      const d = realHistory.reduce((a, p) => a + p.events_down, 0);
      const o = realHistory.reduce((a, p) => a + p.events_out, 0);
      return { new: n, up: u, down: d, out: o, total: n + u + d + o };
    }
    return {
      new: last.events_new,
      up: last.events_up,
      down: last.events_down,
      out: last.events_out,
      total: sum,
    };
  }, [realHistory]);

  const riskBreakdown = useMemo(() => {
    // Only show component breakdown when history carries market_risk consistently.
    const withRisk = realHistory.filter((p) => p.market_risk != null);
    if (withRisk.length < 1 && highRisk == null) return null;
    return { highRisk: highRisk ?? withRisk[withRisk.length - 1]?.market_risk ?? null };
  }, [realHistory, highRisk]);

  return (
    <div
      className="mp2-market-state"
      data-testid="market-state-visual"
      data-fabricated-visual-count="0"
      data-history-points={realHistory.length}
    >
      {/* Breadth */}
      <section className="mp2-state-block" aria-label="Breadth">
        <p className="mp2-kicker">Breadth</p>
        <div className="mp2-breadth-bars tall" aria-hidden>
          <span className="up" style={{ width: `${(rising / breadthTotal) * 100}%` }} />
          <span className="flat" style={{ width: `${(neutral / breadthTotal) * 100}%` }} />
          <span className="down" style={{ width: `${(falling / breadthTotal) * 100}%` }} />
        </div>
        <div className="mp2-breadth-legend">
          <span className="pos">升 {rising}</span>
          <span>中 {neutral}</span>
          <span className="neg">降 {falling}</span>
        </div>
        {breadthSpark ? (
          <div className="mp2-state-spark-row">
            <MetricSpark
              points={breadthSpark}
              expectedIntervalMs={5 * 60 * 1000}
              positive={(breadthSpark[breadthSpark.length - 1]?.value ?? 0) >= 0}
              width={160}
              height={28}
            />
            <span className="muted">24h</span>
          </div>
        ) : (
          <p className="mp2-nodata" style={{ marginTop: 6 }}>
            {loading ? "…" : "NO DATA · 尚無歷史快照"}
          </p>
        )}
      </section>

      {/* Regime */}
      <section className="mp2-state-block" aria-label="Regime">
        <p className="mp2-kicker">Regime</p>
        <div className={`mp2-regime-hero${regimeTone(regime)}`}>{regime}</div>
        {regimeTimeline.length >= 2 ? (
          <div className="mp2-regime-timeline" aria-hidden>
            {regimeTimeline.map((s, i) => {
              const span = Math.max(1, s.to - s.from);
              const total = Math.max(
                1,
                regimeTimeline[regimeTimeline.length - 1].to - regimeTimeline[0].from,
              );
              const w = Math.max(4, (span / total) * 100);
              return (
                <span
                  key={`${s.regime}-${i}`}
                  className={`seg${regimeTone(s.regime).trim()}`}
                  style={{ flexGrow: w }}
                  title={s.regime}
                />
              );
            })}
          </div>
        ) : (
          <p className="mp2-nodata">NO DATA · 無 Regime 時間軸</p>
        )}
      </section>

      {/* Risk */}
      <section className="mp2-state-block" aria-label="Risk">
        <p className="mp2-kicker">Risk</p>
        <RiskGauge highRisk={highRisk} universe={universe} />
        {riskBreakdown?.highRisk != null ? (
          <p className="muted" style={{ fontSize: "0.75rem", marginTop: 4 }}>
            高風險／過熱標的 {riskBreakdown.highRisk}
          </p>
        ) : (
          <p className="mp2-nodata">NO DATA · 無風險拆解</p>
        )}
      </section>

      {/* Opportunity Pipeline */}
      <section className="mp2-state-block" aria-label="Opportunity Pipeline">
        <p className="mp2-kicker">Opportunity Pipeline</p>
        <PipelineBars
          stages={[
            { key: "scanner", label: "Scanner", value: scannerCount },
            { key: "radar", label: "Radar", value: radarCount },
            { key: "trade", label: "Trade", value: tradeCount },
            { key: "qualified", label: "Qualified", value: qualifiedCount },
          ]}
        />
        <p className="muted" style={{ fontSize: "0.6875rem", marginTop: 4 }}>
          Radar ≠ Trade · 觀察排名非交易推薦
        </p>
      </section>

      {/* Radar Activity */}
      <section className="mp2-state-block" aria-label="Radar Activity">
        <p className="mp2-kicker">Radar Activity · 24h</p>
        {activitySpark ? (
          <div className="mp2-state-spark-row">
            <MetricSpark
              points={activitySpark}
              expectedIntervalMs={5 * 60 * 1000}
              width={160}
              height={28}
              positive
            />
            <span className="mono">{radarCount}</span>
          </div>
        ) : (
          <p className="mp2-nodata">NO DATA · 尚無 Radar 趨勢</p>
        )}
        {activityEvents && activityEvents.total > 0 ? (
          <div className="mp2-event-chips">
            <span className="pos">NEW {activityEvents.new}</span>
            <span className="pos">UP {activityEvents.up}</span>
            <span className="neg">DOWN {activityEvents.down}</span>
            <span className="neg">OUT {activityEvents.out}</span>
          </div>
        ) : (
          <p className="mp2-nodata" style={{ marginTop: 4 }}>
            NO DATA · 無事件計數
          </p>
        )}
      </section>
    </div>
  );
}
