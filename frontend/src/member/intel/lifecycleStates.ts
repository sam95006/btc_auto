/**
 * Member Web Intelligence lifecycle / presentation states (UX-B).
 * Each state must remain distinct — never collapse UNAVAILABLE into a zero.
 */

export const LIFECYCLE_STATES = [
  "OBSERVING",
  "AI_ANALYZING",
  "AI_SUGGESTION",
  "RISK_REVIEW",
  "READY",
  "ENTERED",
  "MANAGING",
  "EXITED",
  "BLOCKED",
  "ABSTAINED",
  "SIMULATION",
  "HISTORICAL_REPLAY",
  "DEMO_DATA",
  "UNAVAILABLE",
  "STALE",
] as const;

export type LifecycleState = (typeof LIFECYCLE_STATES)[number];

export const MEMBER_POSTURES = ["LONG", "SHORT", "WAIT", "ABSTAIN"] as const;
export type MemberPosture = (typeof MEMBER_POSTURES)[number];

export const LIFECYCLE_HINT: Record<LifecycleState, string> = {
  OBSERVING: "Watching markets — no suggestion yet",
  AI_ANALYZING: "Model running — not an order",
  AI_SUGGESTION: "Suggestion only — never a filled order",
  RISK_REVIEW: "Risk gate review",
  READY: "Ready for human disposition — not entered",
  ENTERED: "Human-confirmed entry (advisory)",
  MANAGING: "Open thesis management",
  EXITED: "Closed / exited",
  BLOCKED: "Gate blocked",
  ABSTAINED: "Explicit abstention",
  SIMULATION: "Simulation — not live",
  HISTORICAL_REPLAY: "Replay — not live",
  DEMO_DATA: "Fixture / demo catalog",
  UNAVAILABLE: "No value — never render as 0",
  STALE: "As-of lag — not live",
};

export function isLifecycleState(value: string): value is LifecycleState {
  return (LIFECYCLE_STATES as readonly string[]).includes(value);
}
