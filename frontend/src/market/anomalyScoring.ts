import { ANOMALY_CONFIG } from "./anomalyConfig";
import type { AnomalyFreshness, AnomalySeverity, MarketAnomalyEvidence } from "./anomalyTypes";

export function computeAnomalyScore(
  severity: AnomalySeverity,
  freshness: AnomalyFreshness,
  evidence: MarketAnomalyEvidence,
  firstSeenAt: number,
  now: number,
): number {
  const w = ANOMALY_CONFIG.scoreWeights;
  let score = w.severity[severity];
  if (freshness === "LIVE") score += w.freshnessLive;
  else if (freshness === "DELAYED") score += w.freshnessDelayed;
  const factors = evidence.factorCount ?? 1;
  score += Math.min(24, factors * w.perFactor);
  const minutes = Math.max(0, (now - firstSeenAt) / 60_000);
  score += Math.min(w.persistenceCap, minutes * w.persistencePerMinute);
  return Math.round(Math.min(100, Math.max(0, score)));
}

export function severityFromMagnitude(absPct: number, tiers: [number, number, number]): AnomalySeverity {
  if (absPct >= tiers[2]) return "CRITICAL";
  if (absPct >= tiers[1]) return "HIGH";
  if (absPct >= tiers[0]) return "MEDIUM";
  return "LOW";
}
