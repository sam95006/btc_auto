/** Wave 4 — honest decision funnel formatting (no synthetic defaults). */

export const NO_DATA = "NO_DATA" as const;

export type FunnelStage = {
  key: string;
  label: string;
  value: number | null | undefined;
};

export type FunnelDisplay = {
  stages: { key: string; label: string; display: string }[];
  hasData: boolean;
  summary: string;
};

/** Never substitute fake funnel counts (e.g. 128/24/6). */
export function formatFunnelValue(
  value: number | null | undefined,
  dataAvailable = true,
): string {
  if (!dataAvailable) return NO_DATA;
  if (value == null || Number.isNaN(value)) return NO_DATA;
  return String(value);
}

export function buildFunnelDisplay(
  stages: FunnelStage[],
  dataAvailable = true,
): FunnelDisplay {
  const mapped = stages.map((s) => ({
    key: s.key,
    label: s.label,
    display: formatFunnelValue(s.value, dataAvailable),
  }));
  const hasData =
    dataAvailable && mapped.some((s) => s.display !== NO_DATA);
  const summary = hasData
    ? mapped.map((s) => `${s.label}: ${s.display}`).join(" → ")
    : NO_DATA;
  return { stages: mapped, hasData, summary };
}

export function isSyntheticFunnelDefault(counts: number[]): boolean {
  /** Guard against known placeholder funnel triple. */
  if (counts.length !== 3) return false;
  return counts[0] === 128 && counts[1] === 24 && counts[2] === 6;
}
