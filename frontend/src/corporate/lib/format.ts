/** Presentation-only formatting for backend-provided numbers. Never invents a
 * value — a null/undefined input renders as an explicit dash. */

export function fmtPrice(v: number | null | undefined): string {
  if (typeof v !== "number" || !isFinite(v)) return "—";
  const digits = v >= 100 ? 2 : v >= 1 ? 3 : 5;
  return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: digits });
}

export function fmtPct(v: number | null | undefined): string {
  if (typeof v !== "number" || !isFinite(v)) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

export function fmtVol(v: number | null | undefined): string {
  if (typeof v !== "number" || !isFinite(v)) return "—";
  if (v >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return v.toFixed(0);
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "—" : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function ago(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  const s = Math.max(0, Math.round((Date.now() - d.getTime()) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  return `${Math.round(s / 3600)}h ago`;
}

export const symOf = (s: string): string => s.replace("USDT", "");
