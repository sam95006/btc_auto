import { useEffect } from "react";
import { useLocation } from "react-router-dom";

/** Scroll to hash targets for documentation deep links (MVP-14/19). */
export function useHashScroll() {
  const { hash, pathname, search } = useLocation();
  useEffect(() => {
    if (!hash) return;
    const id = decodeURIComponent(hash.replace(/^#/, ""));
    const tryScroll = () => {
      const el = document.getElementById(id);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
        return true;
      }
      return false;
    };
    if (tryScroll()) return;
    const t = window.setTimeout(tryScroll, 80);
    return () => window.clearTimeout(t);
  }, [hash, pathname, search]);
}
