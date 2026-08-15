import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { changeMemberWatchlist, getMemberWatchlist } from "../services/stagingApi";
import { useAuth } from "./AuthContext";

type WatchCtx = {
  symbols: string[];
  has: (symbol: string) => boolean;
  toggle: (symbol: string) => Promise<void>;
};

const Ctx = createContext<WatchCtx | null>(null);

export function WatchlistProvider({ children }: { children: ReactNode }) {
  const { session } = useAuth();
  const [symbols, setSymbols] = useState<string[]>([]);

  useEffect(() => {
    if (!session) {
      setSymbols([]);
      return;
    }
    void getMemberWatchlist().then((response) => setSymbols(response.symbols)).catch(() => setSymbols([]));
  }, [session]);

  const has = useCallback((symbol: string) => symbols.includes(symbol), [symbols]);

  const toggle = useCallback(
    (symbol: string) => {
      const add = !symbols.includes(symbol);
      return changeMemberWatchlist(symbol, add).then((response) => setSymbols(response.symbols));
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
