/**
 * Pure outcome math for MVP-22D (forward return / MFE / MAE).
 * No recommendation / trading coupling.
 */
import type { AnomalyDirection } from "./anomalyTypes";

export function forwardReturnPct(referencePrice: number, observedPrice: number): number {
  if (!(referencePrice > 0) || !Number.isFinite(observedPrice)) return 0;
  return ((observedPrice - referencePrice) / referencePrice) * 100;
}

/**
 * Update running MFE/MAE from a live price tick.
 * UP: MFE = max upside; MAE = max downside.
 * DOWN: MFE = max downside; MAE = max upside.
 * Else: MFE = max abs move up; MAE = max abs move down.
 */
export function updateExcursions(
  referencePrice: number,
  price: number,
  direction: AnomalyDirection | undefined,
  mfe: number,
  mae: number,
): { mfe: number; mae: number } {
  if (!(referencePrice > 0) || !Number.isFinite(price)) return { mfe, mae };
  const up = ((price - referencePrice) / referencePrice) * 100;
  const down = ((referencePrice - price) / referencePrice) * 100;
  if (direction === "UP") {
    return { mfe: Math.max(mfe, Math.max(0, up)), mae: Math.max(mae, Math.max(0, down)) };
  }
  if (direction === "DOWN") {
    return { mfe: Math.max(mfe, Math.max(0, down)), mae: Math.max(mae, Math.max(0, up)) };
  }
  return { mfe: Math.max(mfe, Math.max(0, up)), mae: Math.max(mae, Math.max(0, down)) };
}

export function median(values: number[]): number | null {
  if (!values.length) return null;
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 === 0 ? (s[mid - 1]! + s[mid]!) / 2 : s[mid]!;
}
