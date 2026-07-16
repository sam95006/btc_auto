export type PriceOiQuadrant =
  | "PRICE_UP_OI_UP"
  | "PRICE_UP_OI_DOWN"
  | "PRICE_DOWN_OI_UP"
  | "PRICE_DOWN_OI_DOWN"
  | "INSUFFICIENT";

export function classifyPriceOiQuadrant(
  priceChange5mPct: number | null | undefined,
  oiChange5mPct: number | null | undefined,
  minPricePct = 0.03,
  minOiPct = 0.03,
): PriceOiQuadrant {
  if (priceChange5mPct == null || oiChange5mPct == null) return "INSUFFICIENT";
  if (Math.abs(priceChange5mPct) < minPricePct || Math.abs(oiChange5mPct) < minOiPct) {
    return "INSUFFICIENT";
  }
  const priceUp = priceChange5mPct > 0;
  const oiUp = oiChange5mPct > 0;
  if (priceUp && oiUp) return "PRICE_UP_OI_UP";
  if (priceUp && !oiUp) return "PRICE_UP_OI_DOWN";
  if (!priceUp && oiUp) return "PRICE_DOWN_OI_UP";
  return "PRICE_DOWN_OI_DOWN";
}

export function quadrantExplanation(q: PriceOiQuadrant): string {
  switch (q) {
    case "PRICE_UP_OI_UP":
      return "Price up with OI up may indicate new participation; requires confirmation.";
    case "PRICE_UP_OI_DOWN":
      return "Price up with OI down may indicate short covering possibility; context only.";
    case "PRICE_DOWN_OI_UP":
      return "Price down with OI up may indicate new short participation; requires confirmation.";
    case "PRICE_DOWN_OI_DOWN":
      return "Price down with OI down may indicate long liquidation possibility; context only.";
    default:
      return "Insufficient 5m price/OI window — Collecting.";
  }
}
