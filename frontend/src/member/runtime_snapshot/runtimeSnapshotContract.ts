/**
 * V18.1 Phase B — shared public-safe Runtime Snapshot contract (web).
 * Consumes /api/public/runtime-snapshot — never private conductor imports.
 */

export const RUNTIME_SNAPSHOT_SCHEMA = "v18_1_runtime_snapshot_public_v1";

export type PublicRuntimeState =
  | "RUNNING"
  | "DEGRADED"
  | "PAUSED"
  | "STOPPED"
  | "UNAVAILABLE";

export type RuntimeFreshness =
  | "FRESH"
  | "STALE"
  | "RUNTIME_STOPPED"
  | "UNAVAILABLE"
  | "LIVE_PARTIAL_DEGRADED"
  | "LIVE_READ_ONLY";

export type RuntimeSnapshot = {
  schema: string;
  ok: boolean;
  runtime_state: PublicRuntimeState | string;
  runtime_started_at: string | null;
  runtime_last_cycle_at: string | null;
  data_freshness: RuntimeFreshness | string;
  source_health: {
    status: string;
    source_read_success_count: number;
    source_read_failure_count: number;
    live_records_ingested: number;
    records_quarantined: number;
  };
  universe_funnel: {
    contracts_scanned: number | null;
    eligible: number | null;
    observe_only: number | null;
    blocked: number | null;
    candidates: number | null;
    display: Record<string, string>;
    available: boolean;
  };
  decision_counts: {
    LONG: number | null;
    SHORT: number | null;
    WAIT: number | null;
    ABSTAIN: number | null;
    BLOCK: number | null;
    display: Record<string, string>;
    available: boolean;
  };
  top_opportunities: Array<{
    rank: number;
    market: string;
    contract: string;
    side_hint: string;
    note: string;
  }>;
  shadow_status: {
    shadow_opened_count: number;
    shadow_closed_count: number;
    last_decision: string | null;
    last_symbol: string | null;
    virtual_research_position: boolean;
    sealed: boolean;
  };
  AI_gateway_status: {
    health: string;
    AI_requests: number;
    AI_success: number;
    AI_timeout: number;
    AI_invalid_json: number;
  };
  degraded_reasons: string[];
  actual_ordered: false;
  actual_filled: false;
  data_class: string;
  as_of: string;
  lineage_id: string;
  display_label: string;
  chrome_label: string;
  is_live_view: boolean;
  last_updated: string | null;
  note?: string;
};

export const REQUIRED_RUNTIME_SNAPSHOT_FIELDS = [
  "runtime_state",
  "runtime_started_at",
  "runtime_last_cycle_at",
  "data_freshness",
  "source_health",
  "universe_funnel",
  "decision_counts",
  "top_opportunities",
  "shadow_status",
  "AI_gateway_status",
  "degraded_reasons",
  "actual_ordered",
  "actual_filled",
  "data_class",
  "as_of",
  "lineage_id",
] as const;

export const FORBIDDEN_RUNTIME_PRIVATE_FIELDS = [
  "founder_capital",
  "account_balance",
  "order_id",
  "exchange_order_id",
  "exact_entry",
  "exact_stop",
  "leverage",
  "api_key",
  "api_secret",
  "private_key",
  "lesson_memory",
  "chain_of_thought",
] as const;

/** Honest chrome: never treat STOPPED/STALE/UNAVAILABLE as Live. */
export function runtimeHonestyLabel(snap: Pick<RuntimeSnapshot, "runtime_state" | "is_live_view" | "display_label" | "data_class">): string {
  const state = String(snap.runtime_state || "UNAVAILABLE").toUpperCase();
  if (!snap.is_live_view) {
    if (state === "STOPPED") return snap.display_label || "RUNTIME_STOPPED";
    if (state === "UNAVAILABLE") return "UNAVAILABLE";
    return snap.display_label || "STALE";
  }
  return snap.display_label || snap.data_class || "RUNNING";
}

export function assertNoPrivateRuntimeFields(payload: unknown): number {
  const blob = JSON.stringify(payload ?? {});
  let hits = 0;
  for (const key of FORBIDDEN_RUNTIME_PRIVATE_FIELDS) {
    if (blob.includes(`"${key}"`)) hits += 1;
  }
  return hits;
}
