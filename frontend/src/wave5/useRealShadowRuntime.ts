import { useCallback, useEffect, useRef, useState } from "react";

export type Wave5RuntimeFunnel = {
  marketsScanned?: number;
  marketsEligible?: number;
  candidatesGenerated?: number;
  sixRoleReviewed?: number;
  riskCriticPassed?: number;
  riskCriticBlocked?: number;
  portfolioSelected?: number;
  openShadowPositions?: number;
};

export type Wave5RuntimeStatus = {
  data_status?: string;
  data_source?: string;
  freshness?: string;
  providerStatus?: string;
  fixed_leverage?: number;
  max_open?: number;
  max_pending?: number;
  block_new_entries?: boolean;
  funnel?: Wave5RuntimeFunnel;
  labels?: string[];
  public_market_data_only?: boolean;
  mode?: string;
};

/**
 * Bounded poll of Wave 5 real public shadow runtime status.
 * Never synthesizes fixture funnel counts; NO_DATA when empty.
 */
export function useRealShadowRuntime(pollMs = 8000) {
  const [status, setStatus] = useState<Wave5RuntimeStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const abortRef = useRef<AbortController | null>(null);
  const inFlight = useRef(false);

  const refresh = useCallback(async () => {
    if (typeof document !== "undefined" && document.visibilityState === "hidden") {
      return;
    }
    if (inFlight.current) return;
    inFlight.current = true;
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    try {
      const res = await fetch("/api/nexus/shadow/runtime/status", {
        signal: ac.signal,
        headers: { Accept: "application/json" },
      });
      if (!res.ok) {
        setError(`HTTP_${res.status}`);
        setStatus(null);
        return;
      }
      const body = (await res.json()) as Wave5RuntimeStatus;
      setStatus(body);
      setError(null);
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      setError((e as Error).message || "FETCH_FAILED");
    } finally {
      inFlight.current = false;
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), pollMs);
    const onVis = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
      abortRef.current?.abort();
    };
  }, [pollMs, refresh]);

  const hasRealData =
    status?.data_status === "OK" &&
    (status?.data_source === "REAL_PUBLIC_SHADOW_RUNTIME" ||
      Boolean(status?.funnel && (status.funnel.marketsScanned ?? 0) > 0));

  return { status, error, loading, hasRealData, refresh };
}
