import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { DEFAULT_WATCHLIST_SYMBOLS } from "../mocks/data";

const KEY = "nexus_mp_v1_watchlist";
const KEY_VER = "nexus_mp_v1_watchlist_ver";
const CURRENT_VER = "v2.1-18";

type WatchCtx = {
  symbols: string[];
  has: (symbol: string) => boolean;
  toggle: (symbol: string) => void;
};

const Ctx = createContext<WatchCtx | null>(null);

function load(): string[] {
  try {
    const ver = localStorage.getItem(KEY_VER);
    const raw = localStorage.getItem(KEY);
    if (ver !== CURRENT_VER || !raw) {
      localStorage.setItem(KEY_VER, CURRENT_VER);
      localStorage.setItem(KEY, JSON.stringify(DEFAULT_WATCHLIST_SYMBOLS));
      return [...DEFAULT_WATCHLIST_SYMBOLS];
    }
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) && parsed.length
      ? parsed.map(String)
      : [...DEFAULT_WATCHLIST_SYMBOLS];
  } catch {
    return [...DEFAULT_WATCHLIST_SYMBOLS];
  }
}

export function WatchlistProvider({ children }: { children: ReactNode }) {
  const [symbols, setSymbols] = useState<string[]>(() => load());

  const persist = (next: string[]) => {
    setSymbols(next);
    localStorage.setItem(KEY, JSON.stringify(next));
    localStorage.setItem(KEY_VER, CURRENT_VER);
  };

  const has = useCallback((symbol: string) => symbols.includes(symbol), [symbols]);

  const toggle = useCallback(
    (symbol: string) => {
      persist(symbols.includes(symbol) ? symbols.filter((s) => s !== symbol) : [...symbols, symbol]);
    },
    [symbols]
  );

  const value = useMemo(() => ({ symbols, has, toggle }), [symbols, has, toggle]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useWatchlist() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useWatchlist outside provider");
  return ctx;
}
