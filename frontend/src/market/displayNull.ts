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
  const u = String(v).toUpperCase();
  if (u === "LIVE" || u === "FRESH") return "即時";
  if (u === "DEGRADED" || u === "LIVE_PARTIAL_DEGRADED") return "部分即時／資料降級";
  if (u === "DELAYED") return "延遲";
  if (u === "STALE") return "資料過期";
  if (u === "COLLECTING") return "資料累積中";
  if (u === "UNAVAILABLE") return "資料不可用";
  return v;
}
