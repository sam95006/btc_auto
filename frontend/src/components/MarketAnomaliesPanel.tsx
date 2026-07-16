import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ANOMALY_CONFIG } from "../market/anomalyConfig";
import {
  ANOMALY_TYPE_LABEL,
  type AnomalyFilterCategory,
  type MarketAnomaly,
  type MarketAnomalyType,
} from "../market/anomalyTypes";
import { formatFundingPct } from "../market/fundingConfig";
import { useMarketAnomalies } from "../market/useMarketAnomalies";

const FILTERS: { id: AnomalyFilterCategory; label: string }[] = [
  { id: "all", label: "All" },
  { id: "price", label: "Price" },
  { id: "oi", label: "OI" },
  { id: "funding", label: "Funding" },
  { id: "volume", label: "Volume" },
  { id: "multi", label: "Multi-factor" },
];

function matchesFilter(a: MarketAnomaly, f: AnomalyFilterCategory): boolean {
  if (f === "all") return true;
  if (f === "price") return a.type === "PRICE_ACCELERATION" || a.type === "SPREAD_WIDENING";
  if (f === "oi")
    return a.type === "OI_SURGE" || a.type === "OI_DROP" || a.type === "PRICE_OI_DIVERGENCE";
  if (f === "funding") return a.type === "FUNDING_EXTREME";
  if (f === "volume") return a.type === "VOLUME_EXPANSION";
  if (f === "multi") return a.type === "MULTI_FACTOR_ANOMALY";
  return true;
}

function severityClass(s: MarketAnomaly["severity"]): string {
  return `anomaly-sev anomaly-sev-${s.toLowerCase()}`;
}

function AnomalyCard({ a }: { a: MarketAnomaly }) {
  const ev = a.evidence;
  return (
    <article className="panel-card anomaly-card-item">
      <div className="anomaly-card-head">
        <div>
          <strong className="mono">{a.symbol.replace("USDT", "")}</strong>
          <span className="anomaly-type-label">{ANOMALY_TYPE_LABEL[a.type]}</span>
        </div>
        <div className="anomaly-card-badges">
          <span className={severityClass(a.severity)}>{a.severity}</span>
          <span className="anomaly-score mono" title={ANOMALY_CONFIG.scoreDisclaimer}>
            Score {a.score}
          </span>
        </div>
      </div>
      <h3 className="anomaly-card-title">{a.title}</h3>
      <p className="muted anomaly-card-explain">{a.explanation}</p>
      <div className="anomaly-meta mono muted">
        {a.direction ? `${a.direction} · ` : ""}
        {a.status} · {a.freshness} · score ranks attention only
      </div>
      <details className="anomaly-evidence-details">
        <summary>Evidence</summary>
        <ul className="anomaly-evidence-list mono">
          {ev.currentPrice != null ? <li>Price {ev.currentPrice.toFixed(2)}</li> : null}
          {ev.priceChange1mPct != null ? <li>Δ1m price {ev.priceChange1mPct.toFixed(2)}%</li> : null}
          {ev.priceChange5mPct != null ? <li>Δ5m price {ev.priceChange5mPct.toFixed(2)}%</li> : null}
          {ev.oiChange5mPct != null ? <li>Δ5m OI {ev.oiChange5mPct.toFixed(2)}%</li> : null}
          {ev.fundingRate != null ? <li>Funding {formatFundingPct(ev.fundingRate)}</li> : null}
          {ev.volumeRatio != null ? <li>Turnover pace {ev.volumeRatio.toFixed(2)}%</li> : null}
          {ev.spreadBps != null ? <li>Spread {ev.spreadBps.toFixed(1)} bps</li> : null}
          {ev.priceOiQuadrant ? <li>{ev.priceOiQuadrant}</li> : null}
        </ul>
      </details>
      <div className="anomaly-times mono muted">
        First {new Date(a.firstSeenAt).toISOString()} · Updated {new Date(a.lastSeenAt).toISOString()}
      </div>
    </article>
  );
}

function AnomalyTableRow({ a }: { a: MarketAnomaly }) {
  return (
    <tr>
      <td className="mono">{a.symbol.replace("USDT", "")}</td>
      <td>{ANOMALY_TYPE_LABEL[a.type]}</td>
      <td><span className={severityClass(a.severity)}>{a.severity}</span></td>
      <td>{a.direction ?? "—"}</td>
      <td className="mono">{a.score}</td>
      <td>{a.status}</td>
      <td>{a.freshness}</td>
      <td className="anomaly-row-explain">{a.explanation}</td>
    </tr>
  );
}

/** Full anomaly radar list — read-only (MVP-22C). */
export function MarketAnomaliesPanel() {
  const rows = useMarketAnomalies();
  const [filter, setFilter] = useState<AnomalyFilterCategory>("all");

  const filtered = useMemo(
    () => rows.filter((a) => matchesFilter(a, filter)),
    [rows, filter],
  );

  return (
    <section className="market-anomalies-panel">
      <div className="section-head">
        <h1 className="section-title">Market Anomaly Radar</h1>
        <p className="muted section-lede">
          Market condition requiring attention — NOT a trade instruction.{" "}
          {ANOMALY_CONFIG.researchDisclaimer}
        </p>
      </div>
      <p className="muted anomaly-score-note">{ANOMALY_CONFIG.scoreDisclaimer}</p>

      <div className="anomaly-filter-row" role="tablist" aria-label="Anomaly filters">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            className={filter === f.id ? "anomaly-filter active" : "anomaly-filter"}
            onClick={() => setFilter(f.id)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <p className="muted anomaly-empty">
          No active anomalies for this filter. Rolling windows may still be Collecting — no synthetic
          events.
        </p>
      ) : (
        <>
          <div className="anomaly-table-wrap desktop-only">
            <table className="anomaly-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Type</th>
                  <th>Severity</th>
                  <th>Dir</th>
                  <th>Score</th>
                  <th>Status</th>
                  <th>Fresh</th>
                  <th>Explanation</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((a) => (
                  <AnomalyTableRow key={a.id} a={a} />
                ))}
              </tbody>
            </table>
          </div>
          <div className="anomaly-card-grid mobile-only">
            {filtered.map((a) => (
              <AnomalyCard key={a.id} a={a} />
            ))}
          </div>
        </>
      )}

      <p className="muted">
        <Link to="/overview">← Back to Market Dashboard</Link>
      </p>
    </section>
  );
}

export function filterAnomaliesForTest(
  rows: MarketAnomaly[],
  f: AnomalyFilterCategory,
): MarketAnomaly[] {
  return rows.filter((a) => matchesFilter(a, f));
}

export type { MarketAnomalyType };
