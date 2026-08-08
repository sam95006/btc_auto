import type { PublicPlan } from "../member/public_entitlements_v18_2";

/** Centralized capability authority for paid-value surfaces (no Billing activation). */
export const PRODUCT_CAPABILITIES = {
  FREE: [
    "Market Home (limited Radar depth)",
    "Pulse + live ticker",
    "Watchlist (limited)",
    "Alerts (limited)",
    "Market Terminal chart",
    "NEX AI (limited)",
  ],
  PRO: [
    "Real-time full Live Radar",
    "Rank history",
    "Full alerts",
    "Full watchlist",
    "Terminal intelligence + evidence",
    "Larger NEX AI allowance",
  ],
  RESEARCH: [
    "Advanced derivatives context",
    "Historical analogues",
    "Decision history depth",
    "Data quality tools",
    "Deep evidence / research export (where implemented)",
  ],
} as const;

export const FREE_RADAR_ROW_CAP = 12;
export const FREE_WATCHLIST_SOFT_CAP = 10;

export function isFreePlan(plan: PublicPlan | string | null | undefined): boolean {
  return !plan || plan === "FREE" || plan === "VISITOR";
}

export function requiresPro(plan: PublicPlan | string | null | undefined): boolean {
  return isFreePlan(plan);
}

export function requiresResearch(plan: PublicPlan | string | null | undefined): boolean {
  return plan !== "RESEARCH" && plan !== "ENTERPRISE";
}
