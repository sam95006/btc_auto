import { useEffect, useState } from "react";
import type { RuntimeSnapshot } from "./runtimeSnapshotContract";
import { bindRuntimeSnapshotToFunnel } from "./bindRuntimeSnapshot";
import type { LiveFunnelFirstScreenModel } from "../live_funnel/liveFunnelModels";

type BoundState = {
  loading: boolean;
  error: string | null;
  snapshot: RuntimeSnapshot | null;
  model: LiveFunnelFirstScreenModel | null;
};

const DEFAULT_URL = "/api/public/runtime-snapshot";

/**
 * Fetch live Runtime Snapshot from public binder (fail-closed on error).
 */
export function useRuntimeSnapshot(url: string = DEFAULT_URL): BoundState {
  const [state, setState] = useState<BoundState>({
    loading: true,
    error: null,
    snapshot: null,
    model: null,
  });

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        const resp = await fetch(url, { method: "GET", cache: "no-store" });
        if (!resp.ok) {
          throw new Error(`runtime_snapshot_http_${resp.status}`);
        }
        const snap = (await resp.json()) as RuntimeSnapshot;
        if (cancelled) return;
        setState({
          loading: false,
          error: null,
          snapshot: snap,
          model: bindRuntimeSnapshotToFunnel(snap),
        });
      } catch (err) {
        if (cancelled) return;
        setState({
          loading: false,
          error: err instanceof Error ? err.message : "runtime_snapshot_unavailable",
          snapshot: null,
          model: null,
        });
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [url]);

  return state;
}
