/**
 * PUB-G — Public V1 UI → DTO traceability contract (TypeScript mirror).
 * LIVE mode must not surface MOCK/DEMO values. Bind only public DTO paths.
 */

export const PUBLIC_UI_TRACE_SCHEMA = "public.intelligence.v1" as const;
export const PUBLIC_UI_TRACE_PROGRAM = "NEXUS_PUBLIC_V1_UI_DATA_TRACEABILITY" as const;

export type UiComponentKind =
  | "card"
  | "table"
  | "chart"
  | "gauge"
  | "chip"
  | "notification"
  | "decision_summary";

export type UiMode = "LIVE" | "DEMO" | "MOCK";

export type FreshnessState =
  | "FRESH"
  | "STALE"
  | "DEGRADED"
  | "UNAVAILABLE"
  | "DEMO";

export interface UiDtoBinding {
  componentId: string;
  page: string;
  kind: UiComponentKind;
  mode: UiMode;
  dtoPath: string;
  valueSource: "LIVE" | "DEMO" | "MOCK";
  freshnessState: FreshnessState;
  staleIndicatorPresent: boolean;
  unavailableIndicatorPresent: boolean;
}

export interface TraceabilityCounters {
  visible_mock_value_count: number;
  unmapped_live_component_count: number;
  private_field_binding_count: number;
  stale_without_indicator: number;
  unavailable_fabrication: number;
}

/** Private fields that must never appear in Member UI bindings. */
export const DENIED_PRIVATE_FIELDS = [
  "strategy_id",
  "strategy_weights",
  "lesson_memory",
  "raw_provider_prompt",
  "prompt",
  "orders",
  "positions",
  "wallet",
  "account_id",
  "api_key",
  "api_secret",
  "execution_route",
  "private_risk",
  "fills",
  "leverage",
  "margin",
] as const;

export function emptyCounters(): TraceabilityCounters {
  return {
    visible_mock_value_count: 0,
    unmapped_live_component_count: 0,
    private_field_binding_count: 0,
    stale_without_indicator: 0,
    unavailable_fabrication: 0,
  };
}

export function leafField(dtoPath: string): string {
  const parts = dtoPath.split(".");
  return parts[parts.length - 1] ?? dtoPath;
}

/**
 * Client-side counter check for a binding inventory.
 * Python gate remains source of truth for CI.
 */
export function computeClientCounters(
  componentIds: string[],
  bindings: UiDtoBinding[],
  mode: UiMode = "LIVE",
): TraceabilityCounters {
  const counters = emptyCounters();
  const byComponent = new Map<string, UiDtoBinding[]>();
  for (const b of bindings) {
    const list = byComponent.get(b.componentId) ?? [];
    list.push(b);
    byComponent.set(b.componentId, list);
  }

  for (const id of componentIds) {
    const rows = byComponent.get(id) ?? [];
    if (rows.length === 0) {
      if (mode === "LIVE") counters.unmapped_live_component_count += 1;
      continue;
    }
    for (const row of rows) {
      const leaf = leafField(row.dtoPath);
      if ((DENIED_PRIVATE_FIELDS as readonly string[]).includes(leaf)) {
        counters.private_field_binding_count += 1;
      }
      if (mode === "LIVE") {
        if (row.valueSource === "MOCK" || row.valueSource === "DEMO") {
          counters.visible_mock_value_count += 1;
        }
        if (row.freshnessState === "STALE" && !row.staleIndicatorPresent) {
          counters.stale_without_indicator += 1;
        }
        if (
          row.freshnessState === "UNAVAILABLE" &&
          !row.unavailableIndicatorPresent
        ) {
          // Treat missing unavailable indicator as fabrication risk on client.
          counters.unavailable_fabrication += 1;
        }
      }
    }
  }
  return counters;
}

export const REQUIRED_LIVE_COUNTERS: TraceabilityCounters = emptyCounters();
