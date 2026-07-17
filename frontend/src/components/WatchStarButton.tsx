import { useState } from "react";
import { isWatched, toggleWatch } from "../market/watchlistStore";

export function WatchStarButton({ symbol, className }: { symbol: string; className?: string }) {
  const [on, setOn] = useState(() => isWatched(symbol));
  return (
    <button
      type="button"
      className={`nx-watch-star ${on ? "on" : ""} ${className || ""}`}
      aria-label={on ? "取消關注" : "加入關注"}
      title={on ? "取消關注" : "加入關注（本機）"}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        const next = toggleWatch(symbol);
        setOn(next.symbols.includes(symbol.toUpperCase()));
      }}
    >
      {on ? "★" : "☆"}
    </button>
  );
}
