/**
 * Research aggregations for anomaly outcomes (MVP-22D).
 * Labels: Observed research outcomes / Insufficient sample — never "win rate".
 */
import { OUTCOME_MIN_SAMPLE_FOR_STATS } from "./anomalyOutcomeConfig";
import { median } from "./anomalyOutcomeMath";
import type { AnomalyOutcome, OutcomeAggregation, OutcomeWindow } from "./anomalyOutcomeTypes";
import type { AnomalySeverity, MarketAnomalyType } from "./anomalyTypes";
import type { LiveSymbol } from "./types";

function windowStats(
  rows: AnomalyOutcome[],
  window: OutcomeWindow,
): Pick<
  OutcomeAggregation,
  | "completedSampleCount"
  | "medianForwardReturnPct"
  | "positiveReturnRate"
  | "medianMfePct"
  | "medianMaePct"
  | "missedOrStaleRate"
  | "sampleLabel"
> & { eventCount: number } {
  const eventCount = rows.length;
  const slices = rows.flatMap((r) => r.outcomes.filter((o) => o.window === window));
  const completed = slices.filter((o) => o.status === "COMPLETE");
  const bad = slices.filter((o) => o.status === "MISSED" || o.status === "STALE");
  const returns = completed
    .map((o) => o.forwardReturnPct)
    .filter((v): v is number => v != null && Number.isFinite(v));
  const mfes = completed
    .map((o) => o.maxFavorableExcursionPct)
    .filter((v): v is number => v != null && Number.isFinite(v));
  const maes = completed
    .map((o) => o.maxAdverseExcursionPct)
    .filter((v): v is number => v != null && Number.isFinite(v));
  const completedSampleCount = completed.length;
  const enough = completedSampleCount >= OUTCOME_MIN_SAMPLE_FOR_STATS;
  return {
    eventCount,
    completedSampleCount,
    medianForwardReturnPct: enough ? median(returns) : null,
    positiveReturnRate:
      enough && returns.length
        ? returns.filter((r) => r > 0).length / returns.length
        : null,
    medianMfePct: enough ? median(mfes) : null,
    medianMaePct: enough ? median(maes) : null,
    missedOrStaleRate: slices.length ? bad.length / slices.length : null,
    sampleLabel: enough ? "Observed research outcomes" : "Insufficient sample",
  };
}

export function aggregateOutcomes(
  rows: AnomalyOutcome[],
  window: OutcomeWindow = "5m",
  filter?: {
    anomalyType?: MarketAnomalyType;
    symbol?: LiveSymbol;
    severity?: AnomalySeverity;
  },
): OutcomeAggregation {
  const filtered = rows.filter((r) => {
    if (filter?.anomalyType && r.anomalyType !== filter.anomalyType) return false;
    if (filter?.symbol && r.symbol !== filter.symbol) return false;
    if (filter?.severity && r.severity !== filter.severity) return false;
    return true;
  });
  const parts: string[] = [];
  if (filter?.anomalyType) parts.push(filter.anomalyType);
  if (filter?.symbol) parts.push(filter.symbol.replace("USDT", ""));
  if (filter?.severity) parts.push(filter.severity);
  parts.push(window);
  const stats = windowStats(filtered, window);
  return {
    keyLabel: parts.join(" · ") || `all · ${window}`,
    anomalyType: filter?.anomalyType,
    symbol: filter?.symbol,
    severity: filter?.severity,
    ...stats,
  };
}

export function summarizeByType(
  rows: AnomalyOutcome[],
  window: OutcomeWindow = "5m",
): OutcomeAggregation[] {
  const types = [...new Set(rows.map((r) => r.anomalyType))];
  return types.map((anomalyType) => aggregateOutcomes(rows, window, { anomalyType }));
}

export function summarizeBySymbol(
  rows: AnomalyOutcome[],
  window: OutcomeWindow = "5m",
): OutcomeAggregation[] {
  const symbols = [...new Set(rows.map((r) => r.symbol))];
  return symbols.map((symbol) => aggregateOutcomes(rows, window, { symbol }));
}
