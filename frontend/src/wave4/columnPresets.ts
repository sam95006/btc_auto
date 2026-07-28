/** Universe column presets — SIMPLE / PRO / QUANT tied to view mode prefs. */

import { loadViewMode, type ViewMode } from "../market/viewPrefs";

export type ColumnPreset = "SIMPLE" | "PRO" | "QUANT";

export type UniverseColumn = {
  id: string;
  label: string;
  presets: ColumnPreset[];
};

export const UNIVERSE_COLUMNS: UniverseColumn[] = [
  { id: "rank", label: "#", presets: ["SIMPLE", "PRO", "QUANT"] },
  { id: "symbol", label: "Symbol", presets: ["SIMPLE", "PRO", "QUANT"] },
  { id: "side", label: "方向", presets: ["SIMPLE", "PRO", "QUANT"] },
  { id: "stage", label: "階段", presets: ["SIMPLE", "PRO", "QUANT"] },
  { id: "opportunity", label: "機會", presets: ["SIMPLE", "PRO", "QUANT"] },
  { id: "confirmation", label: "確認", presets: ["PRO", "QUANT"] },
  { id: "risk", label: "風險", presets: ["SIMPLE", "PRO", "QUANT"] },
  { id: "price5m", label: "價 5m", presets: ["PRO", "QUANT"] },
  { id: "oi5m", label: "持倉 5m", presets: ["PRO", "QUANT"] },
  { id: "turnover", label: "活躍", presets: ["QUANT"] },
  { id: "liquidity", label: "流動性", presets: ["QUANT"] },
  { id: "rankChange", label: "排名", presets: ["PRO", "QUANT"] },
  { id: "freshness", label: "新鮮度", presets: ["PRO", "QUANT"] },
];

export function viewModeToPreset(mode: ViewMode): ColumnPreset {
  return mode === "advanced" ? "PRO" : "SIMPLE";
}

export function resolveColumnPreset(explicit?: ColumnPreset): ColumnPreset {
  if (explicit) return explicit;
  return viewModeToPreset(loadViewMode());
}

export function visibleColumns(preset: ColumnPreset): UniverseColumn[] {
  return UNIVERSE_COLUMNS.filter((c) => c.presets.includes(preset));
}

export function cyclePreset(current: ColumnPreset): ColumnPreset {
  const order: ColumnPreset[] = ["SIMPLE", "PRO", "QUANT"];
  const i = order.indexOf(current);
  return order[(i + 1) % order.length];
}
