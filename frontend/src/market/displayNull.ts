/** Null-safe display helpers — never coerce missing values to numeric 0. */

export function fmtNum(
  v: number | null | undefined,
  digits = 0,
): string {
  if (v == null || Number.isNaN(v)) return "—";
  return digits > 0 ? v.toFixed(digits) : Math.round(v).toString();
}

export function fmtPctNull(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

export function displayOrPending(
  v: string | number | null | undefined,
  pendingLabel = "資料尚不可用",
): string {
  if (v == null || v === "") return pendingLabel;
  return String(v);
}

export function freshnessLabel(v: string | null | undefined): string {
  if (!v) return "更新時間未知";
  return v;
}
