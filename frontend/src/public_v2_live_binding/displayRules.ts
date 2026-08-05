/**
 * PUB2-B display honesty — never render UNAVAILABLE as 0.
 */

export function formatLiveDisplay(
  value: unknown,
  freshness: string,
  completeness: string,
): string {
  const state = (freshness || "").toUpperCase();
  const complete = (completeness || "").toUpperCase();
  const unavailable =
    state === "UNAVAILABLE" ||
    state === "BLOCKED" ||
    complete === "MISSING" ||
    complete === "BLOCKED" ||
    value === null ||
    value === undefined ||
    value === "";

  if (unavailable) {
    if (value === 0 || value === 0.0 || value === "0") {
      return state === "BLOCKED" || complete === "BLOCKED" ? "BLOCKED" : "UNAVAILABLE";
    }
    if (value === null || value === undefined || value === "") {
      return state === "BLOCKED" || complete === "BLOCKED" ? "BLOCKED" : "UNAVAILABLE";
    }
    return String(value);
  }
  if (value === null || value === undefined || value === "") return "UNAVAILABLE";
  return String(value);
}

export function isStale(freshness: string): boolean {
  const s = (freshness || "").toUpperCase();
  return s === "STALE" || s === "DEGRADED";
}
