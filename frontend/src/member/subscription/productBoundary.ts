/** PUB17-D subscription product boundary — member web catalog & nav gate. */

export const MEMBER_BUYABLE_PRODUCTS = [
  { productId: "market_data", label: "Market Data" },
  { productId: "ai_intelligence", label: "AI Intelligence" },
  { productId: "decision_context", label: "Decision Context" },
  { productId: "risk_explanation", label: "Risk Explanation" },
  { productId: "alerts", label: "Alerts" },
  { productId: "historical_comparisons", label: "Historical Comparisons" },
  { productId: "global_market_briefs", label: "Global Market Briefs" },
] as const;

export const MEMBER_FORBIDDEN_PRODUCTS = [
  { productId: "auto_trading", label: "Auto Trading" },
  { productId: "copy_trading", label: "Copy Trading" },
  { productId: "exchange_execution", label: "Exchange Execution" },
  { productId: "private_strategy", label: "Private Strategy" },
  { productId: "founder_portfolio_access", label: "Founder Portfolio Access" },
] as const;

export const FORBIDDEN_MEMBER_NAV_PATHS = [
  "/auto-trading",
  "/copy-trading",
  "/exchange-execution",
  "/private-strategy",
  "/founder-portfolio",
  "/execution",
  "/trade",
  "/place-order",
] as const;

export type MemberBuyableProductId =
  (typeof MEMBER_BUYABLE_PRODUCTS)[number]["productId"];
export type MemberForbiddenProductId =
  (typeof MEMBER_FORBIDDEN_PRODUCTS)[number]["productId"];

const FORBIDDEN_IDS = new Set(
  MEMBER_FORBIDDEN_PRODUCTS.map((p) => p.productId),
);

export function isForbiddenMemberProduct(productId: string): boolean {
  return FORBIDDEN_IDS.has(productId as MemberForbiddenProductId);
}

export function assertMemberNavPathsClean(paths: readonly string[]): void {
  for (const path of paths) {
    if ((FORBIDDEN_MEMBER_NAV_PATHS as readonly string[]).includes(path)) {
      throw new Error(
        `HARD BAN: member web nav includes forbidden path ${path}`,
      );
    }
  }
}

/** member_execution_control_count — must remain 0 for member surfaces. */
export function countMemberExecutionControls(
  surfaces: readonly string[],
): number {
  let count = 0;
  for (const s of surfaces) {
    const id = s.trim().toLowerCase().replace(/-/g, "_");
    if (FORBIDDEN_IDS.has(id as MemberForbiddenProductId)) count += 1;
    if (id === "execution_controls" || id === "execution_control") count += 1;
  }
  return count;
}
