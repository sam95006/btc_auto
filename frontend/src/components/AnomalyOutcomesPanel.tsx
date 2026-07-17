import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  OUTCOME_RESEARCH_DISCLAIMER,
  OUTCOME_SCORE_DISCLAIMER,
} from "../market/anomalyOutcomeConfig";
import {
  summarizeBySymbol,
  summarizeByType,
} from "../market/anomalyOutcomeAggregation";
import type { AnomalyOutcome, OutcomeWindow } from "../market/anomalyOutcomeTypes";
import { ANOMALY_TYPE_LABEL } from "../market/anomalyTypes";
import { useAnomalyOutcomes } from "../market/useAnomalyOutcomes";
import { useLiveMarketFeed } from "../market/useLiveMarketFeed";

const WINDOWS: OutcomeWindow[] = ["5m", "15m", "30m", "60m"];

function fmtPct(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(3)}%`;
}

function fmtRate(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

function OutcomeRow({ row, window }: { row: AnomalyOutcome; window: OutcomeWindow }) {
  const w = row.outcomes.find((o) => o.window === window);
  return (
    <tr>
      <td className="mono">{row.symbol.replace("USDT", "")}</td>
      <td>{ANOMALY_TYPE_LABEL[row.anomalyType]}</td>
      <td>{row.severity}</td>
      <td className="mono">{row.referencePrice.toFixed(2)}</td>
      <td>{w?.status ?? "—"}</td>
      <td className="mono">{fmtPct(w?.forwardReturnPct)}</td>
      <td className="mono">{fmtPct(w?.maxFavorableExcursionPct)}</td>
      <td className="mono">{fmtPct(w?.maxAdverseExcursionPct)}</td>
      <td className="mono muted">{row.score}</td>
    </tr>
  );
}

/** Read-only anomaly outcome research panel (MVP-22D). */
export function AnomalyOutcomesPanel() {
  const rows = useAnomalyOutcomes();
  const feed = useLiveMarketFeed();
  const [window, setWindow] = useState<OutcomeWindow>("5m");

  const pending = useMemo(
    () => rows.filter((r) => r.outcomes.some((o) => o.status === "PENDING")),
    [rows],
  );
  const completed = useMemo(
    () => rows.filter((r) => r.outcomes.some((o) => o.status === "COMPLETE")),
    [rows],
  );
  const byType = useMemo(() => summarizeByType(rows, window), [rows, window]);
  const bySymbol = useMemo(() => summarizeBySymbol(rows, window), [rows, window]);

  return (
    <section className="anomaly-outcomes-panel">
      <div className="section-head">
        <h1 className="section-title">Anomaly Outcome Tracking</h1>
        <p className="muted section-lede">{OUTCOME_RESEARCH_DISCLAIMER}</p>
      </div>
      <p className="muted anomaly-score-note">{OUTCOME_SCORE_DISCLAIMER}</p>
      <p className="outcome-session-banner" role="status">
        Session-based research observation — in-memory only. Reload clears tracking. Not permanent
        history · not a trade signal.
      </p>
      <p className="muted mono outcome-feed-line">
        Feed {feed.feedStatus} · transport {feed.transport} · tracked {rows.length} · pending{" "}
        {pending.length} · with complete {completed.length}
      </p>
      <p className="muted">
        <Link to="/anomalies">← Back to Anomaly Radar</Link>
      </p>

      <div className="anomaly-filter-row" role="tablist" aria-label="Outcome windows">
        {WINDOWS.map((w) => (
          <button
            key={w}
            type="button"
            className={window === w ? "anomaly-filter active" : "anomaly-filter"}
            onClick={() => setWindow(w)}
          >
            {w}
          </button>
        ))}
      </div>

      <h2 className="outcome-subhead">Summary by type ({window})</h2>
      <div className="anomaly-table-wrap">
        <table className="anomaly-table">
          <thead>
            <tr>
              <th>Key</th>
              <th>Events</th>
              <th>Completed</th>
              <th>Median fwd</th>
              <th>Positive rate</th>
              <th>Median MFE</th>
              <th>Median MAE</th>
              <th>Miss/Stale</th>
              <th>Label</th>
            </tr>
          </thead>
          <tbody>
            {byType.length === 0 ? (
              <tr>
                <td colSpan={9} className="muted">
                  No tracked outcomes yet — wait for live anomalies.
                </td>
              </tr>
            ) : (
              byType.map((a) => (
                <tr key={a.keyLabel}>
                  <td>{a.keyLabel}</td>
                  <td className="mono">{a.eventCount}</td>
                  <td className="mono">{a.completedSampleCount}</td>
                  <td className="mono">{fmtPct(a.medianForwardReturnPct)}</td>
                  <td className="mono">{fmtRate(a.positiveReturnRate)}</td>
                  <td className="mono">{fmtPct(a.medianMfePct)}</td>
                  <td className="mono">{fmtPct(a.medianMaePct)}</td>
                  <td className="mono">{fmtRate(a.missedOrStaleRate)}</td>
                  <td>{a.sampleLabel}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <h2 className="outcome-subhead">Summary by symbol ({window})</h2>
      <div className="anomaly-table-wrap">
        <table className="anomaly-table">
          <thead>
            <tr>
              <th>Key</th>
              <th>Events</th>
              <th>Completed</th>
              <th>Median fwd</th>
              <th>Label</th>
            </tr>
          </thead>
          <tbody>
            {bySymbol.length === 0 ? (
              <tr>
                <td colSpan={5} className="muted">
                  Insufficient sample
                </td>
              </tr>
            ) : (
              bySymbol.map((a) => (
                <tr key={a.keyLabel}>
                  <td>{a.keyLabel}</td>
                  <td className="mono">{a.eventCount}</td>
                  <td className="mono">{a.completedSampleCount}</td>
                  <td className="mono">{fmtPct(a.medianForwardReturnPct)}</td>
                  <td>{a.sampleLabel}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <h2 className="outcome-subhead">Pending outcomes</h2>
      <div className="anomaly-table-wrap">
        <table className="anomaly-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Type</th>
              <th>Sev</th>
              <th>Ref</th>
              <th>{window}</th>
              <th>Fwd</th>
              <th>MFE</th>
              <th>MAE</th>
              <th>Score</th>
            </tr>
          </thead>
          <tbody>
            {pending.length === 0 ? (
              <tr>
                <td colSpan={9} className="muted">
                  No pending windows
                </td>
              </tr>
            ) : (
              pending.map((r) => <OutcomeRow key={r.anomalyId} row={r} window={window} />)
            )}
          </tbody>
        </table>
      </div>

      <h2 className="outcome-subhead">Completed outcomes</h2>
      <div className="anomaly-table-wrap">
        <table className="anomaly-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Type</th>
              <th>Sev</th>
              <th>Ref</th>
              <th>{window}</th>
              <th>Fwd</th>
              <th>MFE</th>
              <th>MAE</th>
              <th>Score</th>
            </tr>
          </thead>
          <tbody>
            {completed.length === 0 ? (
              <tr>
                <td colSpan={9} className="muted">
                  No completed windows yet (session-based; reload resets tracking)
                </td>
              </tr>
            ) : (
              completed.map((r) => <OutcomeRow key={r.anomalyId} row={r} window={window} />)
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
