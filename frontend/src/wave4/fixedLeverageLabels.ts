/** Wave 4 — fixed 25x shadow portfolio labels (UI only, no live actions). */

export const FIXED_SHADOW_LEVERAGE = 25 as const;
export const MAX_SHADOW_OPEN_POSITIONS = 2 as const;

export function shadowLeverageLabel(): string {
  return `${FIXED_SHADOW_LEVERAGE}x`;
}

export function portfolioLeverageBadge(): string {
  return `Shadow · ${shadowLeverageLabel()} · max ${MAX_SHADOW_OPEN_POSITIONS} positions`;
}

export function formatPositionLeverage(_requested?: number | null): string {
  return shadowLeverageLabel();
}

export function isLiveTradeAction(label: string): boolean {
  const forbidden = [
    "live trade",
    "mainnet",
    "arm",
    "place order",
    "submit order",
    "real money",
  ];
  const lower = label.toLowerCase();
  return forbidden.some((f) => lower.includes(f));
}
