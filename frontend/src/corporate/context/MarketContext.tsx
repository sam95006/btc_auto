/**
 * Shared live-market context. ONE polled fetch of the backend showcase is
 * distributed to the hero, structure scene and live showcase so the whole page
 * animates from a single backend-provided state. The frontend NEVER fabricates
 * a value here — it only mirrors what the backend returns (including honest
 * UNAVAILABLE / STALE / ERROR states).
 */
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { getMarket } from "../api/client";
import type { MarketShowcase } from "../types";

export type MarketState =
  | { status: "LOADING" }
  | { status: "READY"; data: MarketShowcase }
  | { status: "UNAVAILABLE"; reason?: string }
  | { status: "ERROR" };

const MarketCtx = createContext<MarketState>({ status: "LOADING" });

const POLL_MS = 20000; // backend feed cadence; visual only, not a data value

export function MarketProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<MarketState>({ status: "LOADING" });
  const timer = useRef<number | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const d = await getMarket();
        if (!active) return;
        if (d && d.availability && d.availability !== "READY") {
          setState({ status: "UNAVAILABLE", reason: d.reason });
        } else {
          setState({ status: "READY", data: d });
        }
      } catch {
        if (active) setState({ status: "ERROR" });
      }
    };
    load();
    const tick = () => {
      // Pause polling while the tab is hidden (no wasted requests, no fake data).
      if (!document.hidden) load();
      timer.current = window.setTimeout(tick, POLL_MS);
    };
    timer.current = window.setTimeout(tick, POLL_MS);
    return () => {
      active = false;
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, []);

  return <MarketCtx.Provider value={state}>{children}</MarketCtx.Provider>;
}

export function useMarket(): MarketState {
  return useContext(MarketCtx);
}

/** Convenience: the backend regime value or null (never invented). */
export function regimeOf(state: MarketState): "RISK_ON" | "RISK_OFF" | "NEUTRAL" | null {
  return state.status === "READY" ? state.data.regime?.value ?? null : null;
}

/** A coarse, backend-derived "energy" 0..1 used ONLY to modulate motion.
 * Derived from the backend's own regime/risk decision — it changes how the
 * visualization moves, never what value is displayed. */
export function energyOf(state: MarketState): number {
  if (state.status !== "READY") return 0.28; // dim honestly when not READY
  const regime = state.data.regime?.value;
  const risk = state.data.risk?.value;
  let e = 0.5;
  if (regime === "RISK_ON") e = 0.85;
  else if (regime === "RISK_OFF") e = 0.32;
  else if (regime === "NEUTRAL") e = 0.55;
  if (risk === "elevated") e += 0.1;
  else if (risk === "contained") e -= 0.06;
  return Math.max(0.15, Math.min(1, e));
}
