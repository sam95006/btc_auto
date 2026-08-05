/**
 * PUB2-B — Live UI binding types.
 * Every visible value carries full lineage metadata.
 */

export type FreshnessState =
  | "LIVE"
  | "FRESH"
  | "STALE"
  | "DEGRADED"
  | "UNAVAILABLE"
  | "BLOCKED";

export interface LiveSlotBinding {
  component_id: string;
  slot_id: string;
  mode: "LIVE";
  value_source: "LIVE";
  hardcoded: false;
  fabricated: false;
  source: string;
  field: string;
  unit: string | null;
  as_of: string | null;
  retrieved_at: string;
  freshness: FreshnessState | string;
  completeness: string;
  quality: string;
  lineage: string;
  fallback: string;
  live_field_id: string;
  raw_value: unknown;
  display_value: string;
  display_state: string;
  stale_indicator_present: boolean;
  unavailable_indicator_present: boolean;
  shown_as_zero: boolean;
  demo_data: false;
}

export interface ComponentLiveBinding {
  component_id: string;
  page: string;
  kind: string;
  label: string;
  mode: "LIVE";
  slots: LiveSlotBinding[];
  slot_count: number;
}

export interface LiveBindingsEnvelope {
  ok: boolean;
  mode: "LIVE";
  component_count: number;
  components: Record<string, ComponentLiveBinding>;
  binding_required_keys: string[];
  as_of?: string;
}
