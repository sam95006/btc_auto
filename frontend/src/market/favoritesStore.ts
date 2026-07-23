/**
 * Local favorites foundation (localStorage). Distinct from watchlist;
 * max density kept low for Simple View.
 */

const KEY = "nexus_mi_favorites_v1";
const LIMIT = 20;

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
