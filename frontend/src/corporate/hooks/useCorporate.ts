import { useEffect, useRef, useState } from "react";

export type LoadState<T> =
  | { status: "LOADING" }
  | { status: "READY"; data: T }
  | { status: "UNAVAILABLE"; reason?: string }
  | { status: "ERROR" };

/** Fetch a backend resource with explicit states — never a fabricated fallback. */
export function useResource<T extends { availability?: string; reason?: string }>(
  loader: () => Promise<T>,
  deps: unknown[] = [],
): LoadState<T> {
  const [state, setState] = useState<LoadState<T>>({ status: "LOADING" });
  useEffect(() => {
    let active = true;
    setState({ status: "LOADING" });
    loader()
      .then((d) => {
        if (!active) return;
        if (d && d.availability && d.availability !== "READY") {
          setState({ status: "UNAVAILABLE", reason: d.reason });
        } else {
          setState({ status: "READY", data: d });
        }
      })
      .catch(() => active && setState({ status: "ERROR" }));
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

/** Reveal-on-scroll via IntersectionObserver; respects prefers-reduced-motion. */
export function useReveal<T extends HTMLElement = HTMLDivElement>() {
  const ref = useRef<T | null>(null);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduced || typeof IntersectionObserver === "undefined") {
      setShown(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => e.isIntersecting && (setShown(true), io.disconnect())),
      { threshold: 0.15, rootMargin: "0px 0px -8% 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return { ref, shown };
}
