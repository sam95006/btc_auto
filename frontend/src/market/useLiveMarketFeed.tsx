import { createContext, createElement, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { getLiveMarketFeed, type LiveMarketSnapshot } from "./LiveMarketFeed";
import type { LiveMarketPrice, LiveSymbol, MarketConnectionStatus } from "./types";
import { DISPLAY_TO_USDT } from "./types";

const EMPTY: LiveMarketSnapshot = {
  bySymbol: {},
  feedStatus: "DISCONNECTED",
  transport: "none",
  updatedAt: 0,
};

const LiveMarketContext = createContext<LiveMarketSnapshot>(EMPTY);

/** App-level Mainnet public feed provider (throttled render ~400ms). */
export function LiveMarketProvider({ children }: { children: ReactNode }) {
  const [snap, setSnap] = useState<LiveMarketSnapshot>(EMPTY);
  const lastEmit = useRef(0);
  const pending = useRef<LiveMarketSnapshot | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const feed = getLiveMarketFeed();
    feed.start();
    const unsub = feed.subscribe((next) => {
      const now = Date.now();
      const wait = 400 - (now - lastEmit.current);
      if (wait <= 0) {
        lastEmit.current = now;
        setSnap(next);
        return;
      }
      pending.current = next;
      if (timer.current) return;
      timer.current = setTimeout(() => {
        timer.current = null;
        if (pending.current) {
          lastEmit.current = Date.now();
          setSnap(pending.current);
          pending.current = null;
        }
      }, wait);
    });
    return () => {
      unsub();
      if (timer.current) clearTimeout(timer.current);
      // Keep singleton running across route changes; only stop on full unmount of provider.
      feed.stop();
    };
  }, []);

  return createElement(LiveMarketContext.Provider, { value: snap }, children);
}

export function useLiveMarketFeed(): LiveMarketSnapshot {
  return useContext(LiveMarketContext);
}

export function useLivePrice(displayOrUsdt: string): LiveMarketPrice | undefined {
  const snap = useLiveMarketFeed();
  const key = DISPLAY_TO_USDT[displayOrUsdt.toUpperCase()];
  return key ? snap.bySymbol[key] : undefined;
}

export function useFeedStatus(): MarketConnectionStatus {
  return useLiveMarketFeed().feedStatus;
}

export function useLiveSymbols(): LiveSymbol[] {
  const snap = useLiveMarketFeed();
  return useMemo(
    () => (Object.keys(snap.bySymbol) as LiveSymbol[]).sort(),
    [snap.bySymbol],
  );
}
