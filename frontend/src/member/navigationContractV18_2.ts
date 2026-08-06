/**
 * V18.2 member navigation contract — primary IA simplification.
 * Server mirror: GET /api/public/entitlements/v18_2/navigation-contract
 */
import type { MessageKey } from "../i18n";

export const PRIMARY_MEMBER_NAV_V18_2 = [
  { to: "/home", labelKey: "nav.v182.overview", shortKey: "nav.v182.overview.short" },
  { to: "/scanner", labelKey: "nav.v182.scanner", shortKey: "nav.v182.scanner.short" },
  { to: "/alerts", labelKey: "nav.v182.alerts", shortKey: "nav.v182.alerts.short" },
  { to: "/intelligence", labelKey: "nav.v182.intelligence", shortKey: "nav.v182.intelligence.short" },
] as const satisfies ReadonlyArray<{
  to: string;
  labelKey: MessageKey;
  shortKey: MessageKey;
}>;

export const UTILITY_MEMBER_NAV_V18_2 = [
  { to: "/watchlist", labelKey: "nav.v182.watchlist", shortKey: "nav.v182.watchlist.short" },
  { to: "/nex-ai", labelKey: "nav.nexAi", shortKey: "nav.nexAi.short" },
  { to: "/account", labelKey: "nav.account", shortKey: "nav.account.short" },
] as const satisfies ReadonlyArray<{
  to: string;
  labelKey: MessageKey;
  shortKey: MessageKey;
}>;

export const ENTERPRISE_MEMBER_NAV_V18_2 = [
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

export const FORBIDDEN_MEMBER_PRIMARY_PATHS = [
  "/founder/operator",
  "/founder/live-ops",
  "/founder/diagnostics",
  "/founder/runtime",
] as const;

export function assertV182NavContract() {
  for (const path of FORBIDDEN_MEMBER_PRIMARY_PATHS) {
    const inPrimary = PRIMARY_MEMBER_NAV_V18_2.some((i) => (i.to as string) === path);
    if (inPrimary) {
      throw new Error(`HARD BAN: Founder path in member primary nav: ${path}`);
    }
  }
}

assertV182NavContract();
