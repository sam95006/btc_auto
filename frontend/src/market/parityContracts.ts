/**
 * Product 7.1 parity data contracts — honest status, never coerce missing→0.
 */

export type ParityStatus =
  | "live"
  | "pending"
  | "error"
  | "unavailable"
  | "rules-only";

export type ParityMetric<T> = {
  status: ParityStatus;
  value: T | null;
  label: string;
  freshness: string;
  sampleCount?: number | null;
  coverageNote?: string | null;
  error?: string | null;
  source: string;
};

export function pendingMetric<T>(
  label: string,
  source: string,
  note = "PROVIDER_PENDING",
): ParityMetric<T> {
  return {
    status: "pending",
    value: null,
    label,
    freshness: "更新時間未知",
    sampleCount: null,
    coverageNote: note,
    error: null,
    source,
  };
}

export function errorMetric<T>(label: string, source: string, error: string): ParityMetric<T> {
  return {
    status: "error",
    value: null,
    label,
    freshness: "更新時間未知",
    sampleCount: null,
    coverageNote: null,
    error,
    source,
  };
}

export function statusTag(status: ParityStatus): string {
  switch (status) {
    case "live":
      return "LIVE";
    case "rules-only":
      return "RULES-ONLY";
    case "pending":
      return "PENDING";
    case "error":
      return "ERROR";
    default:
      return "UNAVAILABLE";
  }
}
