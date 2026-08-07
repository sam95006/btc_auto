/**
 * V18.2.8 member product navigation — task-first IA (Chinese primary labels).
 * Server mirror: navigation_contract_v18_2_1()
 */
import type { MessageKey } from "../i18n";
import { FORBIDDEN_MEMBER_PRIMARY_PATHS } from "./navigationContractV18_2";

/** Desktop primary — market intelligence tasks, never Founder execution. */
export const PRIMARY_ACTUAL_PANEL_NAV_V18_2_1 = [
  { to: "/overview", labelKey: "nav.v182.overview", shortKey: "nav.v182.overview.short" },
  { to: "/opportunities", labelKey: "nav.v182.opportunities", shortKey: "nav.v182.opportunities.short" },
  { to: "/scanner", labelKey: "nav.v182.scanner", shortKey: "nav.v182.scanner.short" },
  { to: "/alerts", labelKey: "nav.v182.alerts", shortKey: "nav.v182.alerts.short" },
  { to: "/intelligence", labelKey: "nav.v182.intelligence", shortKey: "nav.v182.intelligence.short" },
] as const satisfies ReadonlyArray<{
  to: string;
  labelKey: MessageKey;
  shortKey: MessageKey;
}>;

/** Utility rail — Watchlist, NEX AI, Account */
export const UTILITY_ACTUAL_PANEL_NAV_V18_2_1 = [
  { to: "/watchlist", labelKey: "nav.v182.watchlist", shortKey: "nav.v182.watchlist.short" },
  { to: "/assistant", labelKey: "nav.nexAi", shortKey: "nav.nexAi.short" },
  { to: "/account", labelKey: "nav.account", shortKey: "nav.account.short" },
] as const satisfies ReadonlyArray<{
  to: string;
  labelKey: MessageKey;
  shortKey: MessageKey;
}>;

export const ENTERPRISE_ACTUAL_PANEL_NAV_V18_2_1 = [
  {
    to: "/organization",
    labelKey: "nav.v182.organization",
    shortKey: "nav.v182.organization.short",
  },
] as const satisfies ReadonlyArray<{
  to: string;
  labelKey: MessageKey;
  shortKey: MessageKey;
}>;

/** Mobile bottom: 總覽 / 找機會 / 掃描器 / 警報 + More */
export const MOBILE_BOTTOM_PRIMARY_V18_2_1 = [
  "/overview",
  "/opportunities",
  "/scanner",
  "/alerts",
] as const;

export function assertV1821ActualPanelNavContract() {
  for (const path of FORBIDDEN_MEMBER_PRIMARY_PATHS) {
    const inPrimary = PRIMARY_ACTUAL_PANEL_NAV_V18_2_1.some((i) => (i.to as string) === path);
    if (inPrimary) {
      throw new Error(`HARD BAN: Founder path in actual panel primary nav: ${path}`);
    }
  }
}

assertV1821ActualPanelNavContract();
