/**
 * Theme provider — SYSTEM / LIGHT / DARK. Default SYSTEM. The user preference is
 * persisted locally (non-sensitive) and applied as data-theme on <html> (removed
 * for SYSTEM so prefers-color-scheme governs). No flash: the initial value is
 * also applied by an inline script in corporate.html before first paint.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type ThemeMode = "system" | "light" | "dark";
const KEY = "nexus.corp.theme";

type Ctx = { mode: ThemeMode; resolved: "light" | "dark"; setMode: (m: ThemeMode) => void };
const ThemeCtx = createContext<Ctx | null>(null);

function readStored(): ThemeMode {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "light" || v === "dark" || v === "system") return v;
  } catch { /* ignore */ }
  return "system";
}

function apply(mode: ThemeMode) {
  const el = document.documentElement;
  if (mode === "system") el.removeAttribute("data-theme");
  else el.setAttribute("data-theme", mode);
}

function systemDark(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-color-scheme: dark)").matches;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(() => readStored());
  const [sysDark, setSysDark] = useState<boolean>(systemDark);

  useEffect(() => {
    apply(mode);
    try { localStorage.setItem(KEY, mode); } catch { /* ignore */ }
  }, [mode]);

  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!mq) return;
    const onChange = () => setSysDark(mq.matches);
    mq.addEventListener?.("change", onChange);
    return () => mq.removeEventListener?.("change", onChange);
  }, []);

  const resolved: "light" | "dark" = mode === "system" ? (sysDark ? "dark" : "light") : mode;
  const setMode = useCallback((m: ThemeMode) => setModeState(m), []);
  const value = useMemo(() => ({ mode, resolved, setMode }), [mode, resolved, setMode]);
  return <ThemeCtx.Provider value={value}>{children}</ThemeCtx.Provider>;
}

export function useTheme(): Ctx {
  const ctx = useContext(ThemeCtx);
  if (!ctx) throw new Error("useTheme requires ThemeProvider");
  return ctx;
}
