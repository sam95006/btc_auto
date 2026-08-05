/**
 * Member Web UX completion — presentation states.
 * Fail-closed: unavailable/empty/error never fabricate LIVE numbers.
 */

export type MemberUxState =
  | "fresh"
  | "stale"
  | "degraded"
  | "pending"
  | "unavailable"
  | "blocked"
  | "empty"
  | "error"
  | "loading";

export const MEMBER_UX_STATES: readonly MemberUxState[] = [
  "fresh",
  "stale",
  "degraded",
  "pending",
  "unavailable",
  "blocked",
  "empty",
  "error",
  "loading",
] as const;

export const UX_STATE_LABEL: Record<MemberUxState, string> = {
  fresh: "FRESH",
  stale: "STALE",
  degraded: "DEGRADED",
  pending: "PENDING",
  unavailable: "UNAVAILABLE",
  blocked: "BLOCKED",
  empty: "EMPTY",
  error: "ERROR",
  loading: "LOADING",
};

export const UX_STATE_HINT: Record<MemberUxState, string> = {
  fresh: "Lineage current · safe to read",
  stale: "As-of lag · do not treat as live",
  degraded: "Partial coverage · treat with caution",
  pending: "Awaiting confirmation or review",
  unavailable: "No value shown · not zero · not fabricated",
  blocked: "Gate closed · do not chase",
  empty: "No rows in scope",
  error: "Load failed · retry or inspect source",
  loading: "Fetching · hold judgment",
};

/** Map DEMO / public freshness labels into UX states without inventing LIVE. */
export function freshnessToUxState(
  freshness: string | null | undefined,
): MemberUxState {
  const f = (freshness || "").toUpperCase();
  if (!f) return "unavailable";
  if (f === "DEMO") return "degraded";
  if (f === "FRESH" || f === "LIVE") return "fresh";
  if (f === "STALE") return "stale";
  if (f === "DEGRADED") return "degraded";
  if (f === "UNAVAILABLE" || f === "MISSING") return "unavailable";
  if (f === "PENDING") return "pending";
  if (f === "BLOCKED") return "blocked";
  if (f === "ERROR") return "error";
  if (f === "LOADING") return "loading";
  if (f === "EMPTY") return "empty";
  return "degraded";
}

export function displayValueForState(
  state: MemberUxState,
  value: string | number | null | undefined,
  fallbackLabel = "—",
): string {
  if (state === "loading") return "…";
  if (state === "unavailable" || state === "error") return fallbackLabel;
  if (state === "empty") return "none";
  if (value === null || value === undefined || value === "") return fallbackLabel;
  return String(value);
}
