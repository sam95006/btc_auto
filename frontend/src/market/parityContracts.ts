/**
 * Product 7.2 parity data contracts — honest status, never coerce missing→0.
 * Extends 7.1 with stale detection, lastAttempted tracking, and provider state machine.
 */

export type ParityStatus =
  | "live"
  | "pending"
  | "error"
  | "unavailable"
  | "stale"
  | "rules-only";

export type ParityMetric<T> = {
  status: ParityStatus;
  value: T | null;
  label: string;
  freshness: string;
  /** ISO timestamp of last fetch attempt (successful or not). */
  lastAttempted?: string | null;
  /** ISO timestamp of last successful data receipt. */
  lastSuccessful?: string | null;
  sampleCount?: number | null;
  coverageNote?: string | null;
  error?: string | null;
  source: string;
};

/**
 * Provider state machine — tracks availability transitions and consecutive failures.
 * Shared by all external-data providers (fearGreed, altcoinSeason, news).
 */
export type ProviderAvailability = "pending" | "available" | "unavailable" | "error";

export type ProviderState = {
  availability: ProviderAvailability;
  lastAttempted: number | null;
  lastSuccessful: number | null;
  consecutiveFailures: number;
  lastError: string | null;
};

export function initialProviderState(): ProviderState {
  return {
    availability: "pending",
    lastAttempted: null,
    lastSuccessful: null,
    consecutiveFailures: 0,
    lastError: null,
  };
}

/** Max age (ms) before a "live" metric is considered stale. */
export const STALE_THRESHOLD_MS = 5 * 60 * 1000; // 5 min

export function isStale(lastSuccessful: number | null): boolean {
  if (lastSuccessful == null) return false;
  return Date.now() - lastSuccessful > STALE_THRESHOLD_MS;
}

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
    lastAttempted: null,
    lastSuccessful: null,
    sampleCount: null,
    coverageNote: note,
    error: null,
    source,
  };
}

export function unavailableMetric<T>(
  label: string,
  source: string,
  note: string,
  state?: Pick<ProviderState, "lastAttempted" | "consecutiveFailures">,
): ParityMetric<T> {
  return {
    status: "unavailable",
    value: null,
    label,
    freshness: "提供者不可用",
    lastAttempted: state?.lastAttempted ? new Date(state.lastAttempted).toISOString() : null,
    lastSuccessful: null,
    sampleCount: null,
    coverageNote: note,
    error: state?.consecutiveFailures
      ? `連續失敗 ${state.consecutiveFailures} 次`
      : null,
    source,
  };
}

export function staleMetric<T>(
  label: string,
  source: string,
  lastSuccessful: number,
  value: T | null,
): ParityMetric<T> {
  const ageMin = Math.round((Date.now() - lastSuccessful) / 60_000);
  return {
    status: "stale",
    value,
    label,
    freshness: `${ageMin} 分鐘前更新（已過期）`,
    lastAttempted: new Date().toISOString(),
    lastSuccessful: new Date(lastSuccessful).toISOString(),
    sampleCount: null,
    coverageNote: "資料超過新鮮度閾值，顯示最後已知值（可能過時）",
    error: null,
    source,
  };
}

export function errorMetric<T>(
  label: string,
  source: string,
  error: string,
  state?: Pick<ProviderState, "lastAttempted" | "lastSuccessful">,
): ParityMetric<T> {
  return {
    status: "error",
    value: null,
    label,
    freshness: "更新失敗",
    lastAttempted: state?.lastAttempted ? new Date(state.lastAttempted).toISOString() : null,
    lastSuccessful: state?.lastSuccessful ? new Date(state.lastSuccessful).toISOString() : null,
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
    case "stale":
      return "STALE";
    case "error":
      return "ERROR";
    default:
      return "UNAVAILABLE";
  }
}

export function statusTagColor(status: ParityStatus): "ok" | "warn" | "err" | "muted" {
  switch (status) {
    case "live":
      return "ok";
    case "rules-only":
      return "muted";
    case "stale":
      return "warn";
    case "error":
      return "err";
    default:
      return "warn";
  }
}
