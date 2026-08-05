import { BoundLiveValue, useLiveBindings } from "../public_v2_live_binding";
import type { LiveSlotBinding } from "../public_v2_live_binding";

/** Renders primary live slots for a page; list bodies stay Empty/UNAVAILABLE until live feeds exist. */
export function LiveSlotStrip({
  bindings,
}: {
  bindings: Array<{ binding: LiveSlotBinding; label: string }>;
}) {
  return (
    <div className="member-card-grid live-slot-strip" aria-label="Live lineage bindings">
      {bindings.map((b) => (
        <BoundLiveValue key={`${b.binding.component_id}.${b.binding.slot_id}`} binding={b.binding} label={b.label} />
      ))}
    </div>
  );
}

export function usePageSlots(
  pairs: Array<[componentId: string, slotId: string, label: string]>,
): { loading: boolean; items: Array<{ binding: LiveSlotBinding; label: string }> } {
  const { slot, loading } = useLiveBindings();
  return {
    loading,
    items: pairs.map(([cid, sid, label]) => ({ binding: slot(cid, sid), label })),
  };
}
