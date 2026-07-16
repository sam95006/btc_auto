/**
 * MVP-22C anomaly thresholds — single config.
 * Research / display parameters only. NOT validated trading rules.
 */
import { FUNDING_CONFIG } from "./fundingConfig";

export const ANOMALY_CONFIG = {
  researchDisclaimer: "Research threshold — not a trade trigger",
  scoreDisclaimer:
    "Anomaly score ranks attention priority, not trade probability.",

  priceAcceleration1mPct: 0.12,
  priceAcceleration5mPct: 0.3,

  oiSurge1mPct: 0.08,
  oiSurge5mPct: 0.2,
  oiSurge15mPct: 0.45,
  oiDrop1mPct: -0.08,
  oiDrop5mPct: -0.2,
  oiDrop15mPct: -0.45,

  divergenceMinPrice5mPct: 0.08,
  divergenceMinOi5mPct: 0.1,

  volumeExpansion5mPct: 0.35,
  spreadWidenBps: 10,

  cooldownMs: 120_000,
  dedupWindowMs: 60_000,
  coolingWeakFactor: 0.55,
  resolvedAfterMs: 180_000,
  maxResolvedHistory: 40,

  scoreWeights: {
    severity: { LOW: 20, MEDIUM: 45, HIGH: 70, CRITICAL: 90 },
    freshnessLive: 10,
    freshnessDelayed: 4,
    perFactor: 8,
    persistencePerMinute: 2,
    persistenceCap: 12,
  },

  fundingElevatedAbsPct: FUNDING_CONFIG.elevatedAbsPct,
  fundingExtremeAbsPct: FUNDING_CONFIG.extremeAbsPct,
} as const;
