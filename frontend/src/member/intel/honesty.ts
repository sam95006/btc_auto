/** Honesty helpers — mirror backend hard bans for Member Intelligence UI. */

import type { LifecycleState } from "./lifecycleStates";

const FIXTURE_MODES = new Set([
  "DEMO_DATA",
  "FIXTURE",
  "STAGING_FIXTURE",
  "SIMULATION",
  "HISTORICAL_REPLAY",
  "BACKTEST",
]);

export function chromeLabelForMode(mode: string): string {
  const m = (mode || "").toUpperCase();
  if (FIXTURE_MODES.has(m)) {
    if (m === "DEMO_DATA" || m === "FIXTURE" || m === "STAGING_FIXTURE") return "DEMO_DATA";
    return m;
  }
  if (m === "LIVE") return "LIVE";
  return m || "UNAVAILABLE";
}

export function assertNotFixtureAsLive(mode: string, label: string): void {
  const m = mode.toUpperCase();
  const l = label.toUpperCase();
  if (FIXTURE_MODES.has(m) && (l === "LIVE" || l === "REALTIME")) {
    throw new Error(`fixture_as_live:${mode}->${label}`);
  }
}

export function assertSuggestionNotFilled(
  state: LifecycleState | string,
  actuallyOrdered: boolean | null | undefined,
  orderFillClaimed: boolean,
): void {
  if (state === "AI_SUGGESTION" && (actuallyOrdered === true || orderFillClaimed)) {
    throw new Error("ai_suggestion_as_filled_order");
  }
}

export function actuallyOrderedDisplay(
  value: boolean | null | undefined,
): string {
  if (value == null) return "UNAVAILABLE";
  return value ? "YES" : "NO";
}

export function containsFake60Guarantee(text: string): boolean {
  const t = text.toLowerCase();
  return (
    t.includes("60% guarantee") ||
    t.includes("guaranteed 60%") ||
    t.includes("60% win rate guaranteed")
  );
}
