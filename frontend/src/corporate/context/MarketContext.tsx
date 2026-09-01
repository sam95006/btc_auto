/**
 * Realtime market context. PRIMARY transport is backend server-push (SSE via the
 * existing public-safe pattern): the browser NEVER connects to Binance. Falls
 * back to bounded polling if SSE fails or goes stale. Exposes the market
 * showcase, the deterministic brief and the intelligence feed, plus a connection
 * status. All values are backend-provided; the frontend never fabricates data.
 */
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { API_ORIGIN, getBrief, getEvents, getMarket } from "../api/client";
import { useLocale } from "../i18n";
import type { EventsFeed, IntelEvent, MarketBrief, MarketRegime, MarketShowcase } from "../types";

export type MarketState =
  | { status: "LOADING" }
  | { status: "READY"; data: MarketShowcase }
  | { status: "UNAVAILABLE"; reason?: string }
  | { status: "ERROR" };

export type RealtimeStatus = "connecting" | "live" | "reconnecting" | "polling";

type Ctx = {
  market: MarketState;
  brief: MarketBrief | null;
  events: EventsFeed | null;
  rt: RealtimeStatus;
};

const MarketCtx = createContext<Ctx>({ market: { status: "LOADING" }, brief: null, events: null, rt: "connecting" });

const POLL_MS = 15000;
const STALE_MS = 22000;

function toState(d: MarketShowcase | null | undefined): MarketState {
  if (!d) return { status: "ERROR" };
  if (d.availability && d.availability !== "READY") return { status: "UNAVAILABLE", reason: d.reason };
  return { status: "READY", data: d };
}

export function MarketProvider({ children }: { children: ReactNode }) {
  const { locale } = useLocale();
  const [market, setMarket] = useState<MarketState>({ status: "LOADING" });
  const [brief, setBrief] = useState<MarketBrief | null>(null);
  const [events, setEvents] = useState<EventsFeed | null>(null);
  const [rt, setRt] = useState<RealtimeStatus>("connecting");
  const lastMsg = useRef<number>(Date.now());

  useEffect(() => {
    let es: EventSource | null = null;
    let pollTimer: number | null = null;
    let watchdog: number | null = null;
    let disposed = false;
    let sseFailures = 0;

    const stopPoll = () => { if (pollTimer) { window.clearInterval(pollTimer); pollTimer = null; } };
    const startPoll = () => {
      if (pollTimer) return;
      setRt((s) => (s === "live" ? s : "polling"));
      const load = async () => {
        if (document.hidden) return;
        try { setMarket(toState(await getMarket(locale))); } catch { setMarket({ status: "ERROR" }); }
        try { setBrief(await getBrief(locale)); } catch { /* keep last */ }
        try { setEvents(await getEvents(locale)); } catch { /* keep last */ }
        lastMsg.current = Date.now();
      };
      load();
      pollTimer = window.setInterval(load, POLL_MS);
    };

    // initial content so the UI is populated immediately (feed/brief history)
    (async () => {
      try { setMarket(toState(await getMarket(locale))); } catch { /* SSE may fill in */ }
      try { setBrief(await getBrief(locale)); } catch { /* ignore */ }
      try { setEvents(await getEvents(locale)); } catch { /* ignore */ }
    })();

    const connectSSE = () => {
      if (disposed || typeof EventSource === "undefined") { startPoll(); return; }
      try {
        es = new EventSource(`${API_ORIGIN}/api/corporate/v1/stream?locale=${encodeURIComponent(locale)}`);
      } catch { startPoll(); return; }
      es.onopen = () => { sseFailures = 0; stopPoll(); setRt("live"); lastMsg.current = Date.now(); };
      es.addEventListener("market_snapshot", (e) => {
        lastMsg.current = Date.now(); setRt("live");
        try { setMarket(toState(JSON.parse((e as MessageEvent).data))); } catch { /* ignore */ }
      });
      es.addEventListener("brief_update", (e) => {
        lastMsg.current = Date.now();
        try { setBrief(JSON.parse((e as MessageEvent).data)); } catch { /* ignore */ }
      });
      const onIntel = (e: Event) => {
        lastMsg.current = Date.now();
        try {
          const d = JSON.parse((e as MessageEvent).data);
          const evt: IntelEvent = {
            ts: new Date().toISOString(), symbol: d.symbol ?? null, kind: d.kind ?? "event",
            severity: "medium", text: d.to ? `${d.symbol ?? "MKT"} ${(d.from ?? "").toUpperCase?.() || d.from} → ${(d.to ?? "").toUpperCase?.() || d.to}` : String(d.text ?? ""),
            source: "binance_usdm_public",
          };
          setEvents((prev) => prev
            ? { ...prev, transitions: [evt, ...prev.transitions].slice(0, 24) }
            : { availability: "READY", transitions: [evt], observations: [] });
        } catch { /* ignore */ }
      };
      es.addEventListener("intelligence_event", onIntel);
      es.addEventListener("regime_change", onIntel);
      es.addEventListener("bye", () => { es?.close(); if (!disposed) connectSSE(); });
      es.onerror = () => {
        setRt("reconnecting");
        sseFailures += 1;
        if (sseFailures >= 3) { es?.close(); es = null; startPoll(); } // give up on SSE → poll
      };
    };

    connectSSE();
    // stale watchdog: if no message for STALE_MS, poll to stay fresh
    watchdog = window.setInterval(() => {
      if (Date.now() - lastMsg.current > STALE_MS) startPoll();
    }, 8000);

    const onVis = () => { if (!document.hidden) lastMsg.current = Date.now(); };
    document.addEventListener("visibilitychange", onVis);

    return () => {
      disposed = true;
      es?.close();
      stopPoll();
      if (watchdog) window.clearInterval(watchdog);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [locale]);

  return <MarketCtx.Provider value={{ market, brief, events, rt }}>{children}</MarketCtx.Provider>;
}

export function useMarket(): MarketState { return useContext(MarketCtx).market; }
export function useBrief(): MarketBrief | null { return useContext(MarketCtx).brief; }
export function useEventsFeed(): EventsFeed | null { return useContext(MarketCtx).events; }
export function useRealtime(): RealtimeStatus { return useContext(MarketCtx).rt; }

export function regimeOf(state: MarketState): MarketRegime {
  return state.status === "READY" ? state.data.regime?.value ?? null : null;
}

export function energyOf(state: MarketState): number {
  if (state.status !== "READY") return 0.28;
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
