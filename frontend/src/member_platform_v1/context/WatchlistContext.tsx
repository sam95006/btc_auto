import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

const KEY = "nexus_mp_v1_watchlist";

type WatchCtx = {
  symbols: string[];
  has: (symbol: string) => boolean;
  toggle: (symbol: string) => void;
};

const Ctx = createContext<WatchCtx | null>(null);

function load(): string[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return ["ETHUSDT", "BTCUSDT"];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.map(String) : ["ETHUSDT", "BTCUSDT"];
  } catch {
    return ["ETHUSDT", "BTCUSDT"];
  }
}

export function WatchlistProvider({ children }: { children: ReactNode }) {
  const [symbols, setSymbols] = useState<string[]>(() => load());

  const persist = (next: string[]) => {
    setSymbols(next);
    localStorage.setItem(KEY, JSON.stringify(next));
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
