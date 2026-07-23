import { useState } from "react";
import { isFavorite, toggleFavorite } from "../market/favoritesStore";

/** Compact local favorite toggle — no server sync. */
export function FavoriteToggle({ symbol }: { symbol: string }) {
  const [on, setOn] = useState(() => isFavorite(symbol));

  return (
    <button
      type="button"
      className={`nx-fav-toggle${on ? " active" : ""}`}
      aria-pressed={on}
      aria-label={on ? `取消收藏 ${symbol}` : `收藏 ${symbol}`}
      title={on ? "取消收藏" : "加入收藏（本地）"}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        const next = toggleFavorite(symbol);
        setOn(next.items.some((i) => i.symbol === symbol.toUpperCase()));
      }}
    >
      {on ? "★" : "☆"}
    </button>
  );
}
