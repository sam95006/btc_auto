import type { MarketConnectionStatus } from "./types";

/** Freshness thresholds (MVP-22A). */
export const FRESH_LIVE_MS = 3000;
export const FRESH_DELAYED_MS = 15000;

export function ageToStatus(
  ageMs: number,
  opts?: { reconnecting?: boolean; restFallback?: boolean; disconnected?: boolean },
): MarketConnectionStatus {
  if (opts?.disconnected) return "DISCONNECTED";
  if (opts?.reconnecting) return "RECONNECTING";
  if (opts?.restFallback) return "REST_FALLBACK";
  if (ageMs <= FRESH_LIVE_MS) return "LIVE";
  if (ageMs <= FRESH_DELAYED_MS) return "DELAYED";
  return "STALE";
}

export function formatAge(ageMs: number): string {
  if (!Number.isFinite(ageMs) || ageMs < 0) return "—";
  if (ageMs < 1000) return `<1s`;
  if (ageMs < 60_000) return `${Math.round(ageMs / 1000)}s`;
  return `${Math.round(ageMs / 60_000)}m`;
}

export function formatUsd(n: number | undefined | null): string {
  if (n == null || !Number.isFinite(n)) return "—";
  if (n >= 1000) {
    return n.toLocaleString("en-US", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
  }
  if (n >= 1) {
    return n.toLocaleString("en-US", { maximumFractionDigits: 4 });
  }
  return n.toLocaleString("en-US", { maximumFractionDigits: 8 });
}
