/**
 * MVP-22C Read-only Market Anomaly Radar types.
 * Attention ranking only — NOT trade instructions · NOT recommendation scoring.
 */
import type { LiveSymbol } from "./types";

export type MarketAnomalyType =
  | "PRICE_ACCELERATION"
  | "OI_SURGE"
  | "OI_DROP"
  | "PRICE_OI_DIVERGENCE"
  | "FUNDING_EXTREME"
  | "VOLUME_EXPANSION"
  | "SPREAD_WIDENING"
  | "MULTI_FACTOR_ANOMALY";

export type AnomalySeverity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type AnomalyDirection = "UP" | "DOWN" | "MIXED" | "NEUTRAL";
export type AnomalyFreshness = "LIVE" | "DELAYED" | "STALE";
export type AnomalyStatus = "NEW" | "ACTIVE" | "COOLING" | "RESOLVED";

export type MarketAnomalyEvidence = {
  currentPrice?: number;
  priceChange1mPct?: number;
  priceChange5mPct?: number;
  oiChange1mPct?: number;
  oiChange5mPct?: number;
  oiChange15mPct?: number;
  fundingRate?: number;
  volumeRatio?: number;
  spreadBps?: number;
  priceOiQuadrant?: string;
  factorCount?: number;
};

export type MarketAnomaly = {
  id: string;
  symbol: LiveSymbol;
  type: MarketAnomalyType;
  severity: AnomalySeverity;
  direction?: AnomalyDirection;
  title: string;
  explanation: string;
  observedAt: number;
  firstSeenAt: number;
  lastSeenAt: number;
  source: "BYBIT_MAINNET_LINEAR";
  freshness: AnomalyFreshness;
  evidence: MarketAnomalyEvidence;
  status: AnomalyStatus;
  score: number;
};

export type AnomalyFilterCategory = "all" | "price" | "oi" | "funding" | "volume" | "multi";

export const ANOMALY_TYPE_LABEL: Record<MarketAnomalyType, string> = {
  PRICE_ACCELERATION: "Price acceleration",
  OI_SURGE: "OI surge",
  OI_DROP: "OI drop",
  PRICE_OI_DIVERGENCE: "Price / OI divergence",
  FUNDING_EXTREME: "Funding extreme",
  VOLUME_EXPANSION: "Turnover expansion",
  SPREAD_WIDENING: "Spread widening",
  MULTI_FACTOR_ANOMALY: "Multi-factor anomaly",
};
