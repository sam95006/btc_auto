import { MARKET_READINESS } from "../demo/marketDashboard";

/** NEXUS Market Readiness Score — demo gauge, not RSI copy (MVP-22). */
export function MarketReadinessGauge() {
  const { score, label, lines } = MARKET_READINESS;
  const pct = Math.max(0, Math.min(100, score));
  return (
    <section className="panel-card readiness-gauge" aria-label="Market Readiness">
      <h2>Market Readiness</h2>
      <p className="muted gauge-sub">NEXUS Market Readiness Score</p>
      <div className="gauge-ring" style={{ ["--gauge-pct" as string]: String(pct) }}>
        <div className="gauge-score mono">{score.toFixed(1)}</div>
        <div className="gauge-label">{label}</div>
      </div>
      <ul className="gauge-lines">
        {lines.map((l) => (
          <li key={l}>{l}</li>
        ))}
      </ul>
    </section>
  );
}
