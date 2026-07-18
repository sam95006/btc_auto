/** Local watchlist v2 — assetClass + crypto preservation (Phase 3). */

const KEY_V1 = "nexus_mi_watchlist_v1";
const KEY = "nexus_mi_watchlist_v2";
const LIMIT = 30;

export type AssetClass = "CRYPTO" | "TOKENIZED_EQUITY" | "EQUITY";

export type WatchItem = {
  symbol: string;
  assetClass: AssetClass;
};

export type WatchlistState = {
  version: 2;
  items: WatchItem[];
  updatedAt: number;
};

function empty(): WatchlistState {
  return { version: 2, items: [], updatedAt: Date.now() };
}

function migrateV1(raw: string): WatchlistState | null {
  try {
    const parsed = JSON.parse(raw) as { version?: number; symbols?: string[] };
    if (!parsed || parsed.version !== 1 || !Array.isArray(parsed.symbols)) return null;
    return {
      version: 2,
      items: parsed.symbols
        .map((s) => String(s || "").toUpperCase())
        .filter((s) => /^[A-Z0-9]+USDT$/.test(s))
        .slice(0, LIMIT)
        .map((symbol) => ({ symbol, assetClass: "CRYPTO" as const })),
      updatedAt: Date.now(),
    };
  } catch {
    return null;
  }
}

export function loadWatchlist(): WatchlistState {
  try {
    const v2 = localStorage.getItem(KEY);
    if (v2) {
      const parsed = JSON.parse(v2) as WatchlistState;
      if (parsed?.version === 2 && Array.isArray(parsed.items)) {
        return {
          version: 2,
          items: parsed.items
            .map((it) => ({
              symbol: String(it.symbol || "").toUpperCase(),
              assetClass: (it.assetClass || "CRYPTO") as AssetClass,
            }))
            .filter((it) => it.symbol)
            .slice(0, LIMIT),
          updatedAt: Number(parsed.updatedAt) || Date.now(),
        };
      }
    }
    const v1 = localStorage.getItem(KEY_V1);
    if (v1) {
      const migrated = migrateV1(v1);
      if (migrated) {
        persist(migrated);
        return migrated;
      }
    }
    return empty();
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

/** Backward-compatible symbol list for crypto UI. */
export function loadWatchlistSymbols(): string[] {
  return loadWatchlist()
    .items.filter((i) => i.assetClass === "CRYPTO")
    .map((i) => i.symbol);
}

export function isWatched(symbol: string, assetClass: AssetClass = "CRYPTO"): boolean {
  const sym = symbol.toUpperCase();
  return loadWatchlist().items.some((i) => i.symbol === sym && i.assetClass === assetClass);
}

export function toggleWatch(symbol: string, assetClass: AssetClass = "CRYPTO"): WatchlistState {
  const sym = symbol.toUpperCase();
  const cur = loadWatchlist();
  const has = cur.items.some((i) => i.symbol === sym && i.assetClass === assetClass);
  const items = has
    ? cur.items.filter((i) => !(i.symbol === sym && i.assetClass === assetClass))
    : [{ symbol: sym, assetClass }, ...cur.items].slice(0, LIMIT);
  const next = { version: 2 as const, items, updatedAt: Date.now() };
  persist(next);
  return next;
}

export function removeWatch(symbol: string, assetClass: AssetClass = "CRYPTO"): WatchlistState {
  const cur = loadWatchlist();
  const next = {
    version: 2 as const,
    items: cur.items.filter((i) => !(i.symbol === symbol.toUpperCase() && i.assetClass === assetClass)),
    updatedAt: Date.now(),
  };
  persist(next);
  return next;
}

export const WATCHLIST_LIMIT = LIMIT;
