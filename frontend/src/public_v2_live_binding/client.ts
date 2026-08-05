/**
 * PUB2-B LIVE bindings client — never merges DEMO/FIXTURE into LIVE.
 */

import type { LiveBindingsEnvelope, LiveSlotBinding } from "./types";

const ENDPOINT = "/api/public/v2/live-bindings";

export async function fetchLiveBindings(
  signal?: AbortSignal,
): Promise<LiveBindingsEnvelope> {
  const res = await fetch(ENDPOINT, {
    method: "GET",
    headers: { Accept: "application/json" },
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`live_bindings_http_${res.status}`);
  }
  const body = (await res.json()) as LiveBindingsEnvelope;
  if (body.mode !== "LIVE") {
    throw new Error("demo_fixture_merge_refused");
  }
  return body;
}

export function slotOf(
  envelope: LiveBindingsEnvelope | null,
  componentId: string,
  slotId?: string,
): LiveSlotBinding | null {
  if (!envelope) return null;
  const comp = envelope.components[componentId];
  if (!comp || !comp.slots.length) return null;
  if (!slotId) return comp.slots[0] ?? null;
  return comp.slots.find((s) => s.slot_id === slotId) ?? null;
}

/** Honest unavailable placeholder when fetch fails — never numeric 0. */
export function unavailableSlot(
  componentId: string,
  slotId: string,
  reason: string,
): LiveSlotBinding {
  const retrieved = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  return {
    component_id: componentId,
    slot_id: slotId,
    mode: "LIVE",
    value_source: "LIVE",
    hardcoded: false,
    fabricated: false,
    source: "LIVE_CLIENT",
    field: slotId,
    unit: null,
    as_of: null,
    retrieved_at: retrieved,
    freshness: "UNAVAILABLE",
    completeness: "MISSING",
    quality: reason,
    lineage: `client_unavailable_${componentId}_${slotId}`,
    fallback: "display_UNAVAILABLE",
    live_field_id: slotId,
    raw_value: null,
    display_value: "UNAVAILABLE",
    display_state: "UNAVAILABLE",
    stale_indicator_present: false,
    unavailable_indicator_present: true,
    shown_as_zero: false,
    demo_data: false,
  };
}
