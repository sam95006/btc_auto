import { useEffect, useState } from "react";
import {
  addServerWatch,
  fetchServerWatchlist,
  isAuthRequired,
  removeServerWatch,
} from "../retention/retentionApi";
import { isWatched as isLocalWatched, toggleWatch } from "../market/watchlistStore";

/**
 * Watch star — prefers server watchlist when authenticated.
 * Falls back to local-only draft with explicit title (not canonical).
 */
export function WatchStarButton({ symbol, className }: { symbol: string; className?: string }) {
  const [on, setOn] = useState(false);
  const [serverMode, setServerMode] = useState(false);

  useEffect(() => {
    let alive = true;
    void (async () => {
      const { res, body } = await fetchServerWatchlist();
      if (!alive) return;
      if (res.status === 401 || isAuthRequired(body)) {
        setServerMode(false);
        setOn(isLocalWatched(symbol));
        return;
      }
      setServerMode(true);
      const items = (body.items as { symbol?: string }[]) || [];
      setOn(items.some((i) => String(i.symbol || "").toUpperCase() === symbol.toUpperCase()));
    })();
    return () => {
      alive = false;
    };
  }, [symbol]);

  return (
    <button
      type="button"
      className={`nx-watch-star ${on ? "on" : ""} ${className || ""}`}
      aria-label={on ? "取消關注" : "加入關注"}
      title={
        serverMode
          ? on
            ? "取消關注（伺服器）"
            : "加入關注（伺服器）"
          : on
            ? "取消關注（本機草稿 · 非 canonical）"
            : "加入關注（本機草稿 · 登入後改用伺服器）"
      }
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        void (async () => {
          if (serverMode) {
            if (on) {
              const { body } = await removeServerWatch(symbol);
              if (!isAuthRequired(body)) {
                const items = (body.items as { symbol?: string }[]) || [];
                setOn(items.some((i) => String(i.symbol || "").toUpperCase() === symbol.toUpperCase()));
                return;
              }
            } else {
              const { body } = await addServerWatch(symbol);
              if (!isAuthRequired(body)) {
                const items = (body.items as { symbol?: string }[]) || [];
                setOn(items.some((i) => String(i.symbol || "").toUpperCase() === symbol.toUpperCase()));
                return;
              }
            }
          }
          const next = toggleWatch(symbol);
          setOn(next.items.some((i) => i.symbol === symbol.toUpperCase() && i.assetClass === "CRYPTO"));
          setServerMode(false);
        })();
      }}
    >
      {on ? "★" : "☆"}
    </button>
  );
}
