/**
 * Favorites persistence data contract (Product 7.2).
 *
 * STORAGE_CONTRACT:
 *   scope:        LOCAL_ONLY — stored in localStorage of this browser only.
 *   sync:         NOT synced across devices. No backend endpoint exists.
 *                 Cross-device sync requires a signed-in user API (NOT implemented).
 *   cloud:        NEVER claimed. Do not show "synced to cloud" without backend confirmation.
 *   version:      v1 — schema migrations must increment version and handle legacy.
 *   limit:        20 favorites max (prevent unbounded growth in localStorage).
 *   persistence:  Survives page refresh; lost on clear-site-data / incognito.
 *
 * Distinct from watchlist (useWatchlistStore) — favorites are operator-curated pins.
 */

const KEY = "nexus_mi_favorites_v1";
const LIMIT = 20;

/**
 * Exported storage contract for UI disclosure.
 */
export const FAVORITES_STORAGE_CONTRACT = {
  scope: "LOCAL_ONLY",
  cloudSync: false,
  crossDeviceSync: false,
  backendRequired: true,
  maxItems: LIMIT,
  storageKey: KEY,
  note: "只存於本瀏覽器 localStorage。不跨裝置，無雲端同步。",
} as const;

export type FavoriteItem = {
  symbol: string;
  note?: string;
  addedAt: number;
};

export type FavoritesState = {
  version: 1;
  items: FavoriteItem[];
  updatedAt: number;
};

function empty(): FavoritesState {
  return { version: 1, items: [], updatedAt: Date.now() };
}

export function loadFavorites(): FavoritesState {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return empty();
    const parsed = JSON.parse(raw) as FavoritesState;
    if (parsed?.version !== 1 || !Array.isArray(parsed.items)) return empty();
    return {
      version: 1,
      items: parsed.items
        .map((it) => ({
          symbol: String(it.symbol || "").toUpperCase(),
          note: it.note ? String(it.note) : undefined,
          addedAt: Number(it.addedAt) || Date.now(),
        }))
        .filter((it) => it.symbol)
        .slice(0, LIMIT),
      updatedAt: Number(parsed.updatedAt) || Date.now(),
    };
  } catch {
    return empty();
  }
}

function persist(state: FavoritesState) {
  try {
    localStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    /* ignore quota */
  }
}

export function isFavorite(symbol: string): boolean {
  const sym = symbol.toUpperCase();
  return loadFavorites().items.some((i) => i.symbol === sym);
}

export function toggleFavorite(symbol: string): FavoritesState {
  const sym = symbol.toUpperCase();
  const cur = loadFavorites();
  const has = cur.items.some((i) => i.symbol === sym);
  const items = has
    ? cur.items.filter((i) => i.symbol !== sym)
    : [{ symbol: sym, addedAt: Date.now() }, ...cur.items].slice(0, LIMIT);
  const next: FavoritesState = { version: 1, items, updatedAt: Date.now() };
  persist(next);
  return next;
}

export function listFavoriteSymbols(): string[] {
  return loadFavorites().items.map((i) => i.symbol);
}

export const FAVORITES_LIMIT = LIMIT;

/**
 * Returns a human-readable disclosure string for UI display.
 * Use this in settings panels to make persistence scope clear to operators.
 */
export function favoritesStorageDisclosure(): string {
  return "收藏清單僅存於本瀏覽器 localStorage（本機）。不會跨裝置同步，不會上傳至雲端。清除網站資料或無痕模式會失去收藏。";
}
