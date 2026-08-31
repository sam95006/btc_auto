/**
 * Lightweight scroll orchestration — no dependency, no scroll hijacking.
 * A single shared rAF loop reads element positions and writes a 0..1 progress
 * either to a CSS variable (--p, for cheap GPU-composited reveals) or to React
 * state (for components that switch discrete stages). prefers-reduced-motion
 * short-circuits everything to the final state so content is always complete
 * and keyboard/scroll behaviour stays native.
 */
import { useEffect, useRef, useState } from "react";

function reducedMotion(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

// ---- one shared scroll/resize scheduler ----
type Sub = () => void;
const subs = new Set<Sub>();
let raf = 0;
function schedule() {
  if (raf) return;
  raf = requestAnimationFrame(() => {
    raf = 0;
    subs.forEach((s) => s());
  });
}
let wired = false;
function ensureListeners() {
  if (typeof window === "undefined" || wired) return;
  window.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("resize", schedule, { passive: true });
  wired = true;
}

/** Progress of an element through the viewport: 0 before it enters, 1 once its
 * top has travelled ~70% up the viewport. Written to `--p` on the element. */
export function useRevealVar<T extends HTMLElement = HTMLDivElement>() {
  const ref = useRef<T | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (reducedMotion()) {
      el.style.setProperty("--p", "1");
      return;
    }
    ensureListeners();
    const update = () => {
      const r = el.getBoundingClientRect();
      const vh = window.innerHeight || 1;
      // enter when top reaches 92% of vh, fully in at 30% of vh
      const p = (0.92 * vh - r.top) / (0.62 * vh);
      el.style.setProperty("--p", String(Math.max(0, Math.min(1, p))));
    };
    const sub: Sub = update;
    subs.add(sub);
    update();
    return () => {
      subs.delete(sub);
    };
  }, []);
  return ref;
}

/** Continuous 0..1 progress of an element across the viewport as React state,
 * throttled to animation frames. Used to drive discrete stage switches. */
export function useStageProgress<T extends HTMLElement = HTMLDivElement>() {
  const ref = useRef<T | null>(null);
  const [progress, setProgress] = useState(reducedMotion() ? 1 : 0);
  useEffect(() => {
    const el = ref.current;
    if (!el || reducedMotion()) return;
    ensureListeners();
    let last = -1;
    const update = () => {
      const r = el.getBoundingClientRect();
      const vh = window.innerHeight || 1;
      const total = r.height + vh;
      const p = (vh - r.top) / total; // 0 when entering bottom, 1 when leaving top
      const clamped = Math.max(0, Math.min(1, p));
      if (Math.abs(clamped - last) > 0.004) {
        last = clamped;
        setProgress(clamped);
      }
    };
    const sub: Sub = update;
    subs.add(sub);
    update();
    return () => {
      subs.delete(sub);
    };
  }, []);
  return { ref, progress };
}

export { reducedMotion };
