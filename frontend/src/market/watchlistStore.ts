/** Local watchlist — no account, bounded, schema-versioned. */

const KEY = "nexus_mi_watchlist_v1";
const LIMIT = 30;

export type WatchlistState = {
  version: 1;
  symbols: string[];
  updatedAt: number;
};

function empty(): WatchlistState {
  return { version: 1, symbols: [], updatedAt: Date.now() };
}

export function loadWatchlist(): WatchlistState {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return empty();
    const parsed = JSON.parse(raw) as WatchlistState;
    if (!parsed || parsed.version !== 1 || !Array.isArray(parsed.symbols)) return empty();
    return {
      version: 1,
      symbols: parsed.symbols
        .map((s) => String(s || "").toUpperCase())
        .filter((s) => /^[A-Z0-9]+USDT$/.test(s))
        .slice(0, LIMIT),
      updatedAt: Number(parsed.updatedAt) || Date.now(),
    };
  } catch {
    return empty();
  }
}

function persist(state: WatchlistState) {
  try {
    localStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    /* ignore */
  }
}

export function isWatched(symbol: string): boolean {
  return loadWatchlist().symbols.includes(symbol.toUpperCase());
}

export function toggleWatch(symbol: string): WatchlistState {
  const sym = symbol.toUpperCase();
  const cur = loadWatchlist();
  const has = cur.symbols.includes(sym);
  const symbols = has ? cur.symbols.filter((s) => s !== sym) : [sym, ...cur.symbols].slice(0, LIMIT);
  const next = { version: 1 as const, symbols, updatedAt: Date.now() };
  persist(next);
  return next;
}

export function removeWatch(symbol: string): WatchlistState {
  const cur = loadWatchlist();
  const next = {
    version: 1 as const,
    symbols: cur.symbols.filter((s) => s !== symbol.toUpperCase()),
    updatedAt: Date.now(),
  };
  persist(next);
  return next;
}

export const WATCHLIST_LIMIT = LIMIT;
