import { useEffect, useState } from "react";
import { fetchLiveBindings, unavailableSlot } from "./client";
import type { LiveBindingsEnvelope, LiveSlotBinding } from "./types";

export function useLiveBindings(): {
  envelope: LiveBindingsEnvelope | null;
  loading: boolean;
  error: string | null;
  slot: (componentId: string, slotId?: string) => LiveSlotBinding;
} {
  const [envelope, setEnvelope] = useState<LiveBindingsEnvelope | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    setLoading(true);
    fetchLiveBindings(ac.signal)
      .then((body) => {
        setEnvelope(body);
        setError(null);
      })
      .catch((err: unknown) => {
        if ((err as { name?: string })?.name === "AbortError") return;
        setEnvelope(null);
        setError(err instanceof Error ? err.message : "live_bindings_unavailable");
      })
      .finally(() => setLoading(false));
    return () => ac.abort();
  }, []);

  function slot(componentId: string, slotId = "default"): LiveSlotBinding {
    const comp = envelope?.components[componentId];
    if (comp?.slots?.length) {
      if (slotId === "default") return comp.slots[0]!;
      return (
        comp.slots.find((s) => s.slot_id === slotId) ??
        unavailableSlot(componentId, slotId, "slot_missing")
      );
    }
    return unavailableSlot(
      componentId,
      slotId,
      error || (loading ? "loading" : "bindings_unavailable"),
    );
  }

  return { envelope, loading, error, slot };
}
