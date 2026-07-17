/** MVP-22D outcome tracking config — research thresholds only. */
import type { OutcomeWindow } from "./anomalyOutcomeTypes";

export const OUTCOME_WINDOWS: { window: OutcomeWindow; ms: number }[] = [
  { window: "5m", ms: 5 * 60_000 },
  { window: "15m", ms: 15 * 60_000 },
  { window: "30m", ms: 30 * 60_000 },
  { window: "60m", ms: 60 * 60_000 },
];

/** Accept price samples within ± this ms of target for COMPLETE. */
export const OUTCOME_TIMESTAMP_TOLERANCE_MS = 15_000;

/** After target+tolerance without a valid sample → MISSED. */
export const OUTCOME_MISS_GRACE_MS = 30_000;

export const OUTCOME_MAX_TRACKED = 200;
export const OUTCOME_MIN_SAMPLE_FOR_STATS = 5;

export const OUTCOME_RESEARCH_DISCLAIMER =
  "Observed research outcomes only — NOT a trade instruction · NOT win rate · NOT expected profit · NOT recommendation input.";

export const OUTCOME_SCORE_DISCLAIMER =
  "Anomaly score ranks attention priority at detection time; outcome metrics do not feed Recommendation, confidence, or Gauge scoring.";
