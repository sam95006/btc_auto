/**
 * MVP-22D Anomaly Outcome Tracking — research only.
 * Observed research outcomes · NOT win rate · NOT trade probability · NOT recommendation input.
 */
import type { AnomalyDirection, AnomalySeverity, MarketAnomalyType } from "./anomalyTypes";
import type { LiveSymbol } from "./types";

export type OutcomeWindow = "5m" | "15m" | "30m" | "60m";
export type OutcomeWindowStatus = "PENDING" | "COMPLETE" | "MISSED" | "STALE";

export type AnomalyWindowOutcome = {
  window: OutcomeWindow;
  targetTimestamp: number;
  observedTimestamp?: number;
  observedPrice?: number;
  forwardReturnPct?: number;
  maxFavorableExcursionPct?: number;
  maxAdverseExcursionPct?: number;
  status: OutcomeWindowStatus;
};

export type AnomalyOutcome = {
  anomalyId: string;
  symbol: LiveSymbol;
  anomalyType: MarketAnomalyType;
  severity: AnomalySeverity;
  direction?: AnomalyDirection;
  score: number;
  observedAt: number;
  referencePrice: number;
  anomalyStatusAtObserve: string;
  freshnessAtObserve: string;
  evidenceSnapshot: Record<string, number | string | undefined>;
  outcomes: AnomalyWindowOutcome[];
  source: "BYBIT_MAINNET_LINEAR";
  researchOnly: true;
  lastUpdatedAt: number;
};

export type OutcomeAggKey = {
  anomalyType?: MarketAnomalyType;
  symbol?: LiveSymbol;
  severity?: AnomalySeverity;
};

export type OutcomeAggregation = {
  keyLabel: string;
  anomalyType?: MarketAnomalyType;
  symbol?: LiveSymbol;
  severity?: AnomalySeverity;
  eventCount: number;
  completedSampleCount: number;
  medianForwardReturnPct: number | null;
  positiveReturnRate: number | null;
  medianMfePct: number | null;
  medianMaePct: number | null;
  missedOrStaleRate: number | null;
  sampleLabel: "Observed research outcomes" | "Insufficient sample";
};
