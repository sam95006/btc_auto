import type { MessageKey } from "../i18n";
import {
  assertMemberNavPathsClean,
  countMemberExecutionControls,
} from "./subscription/productBoundary";
import {
  ENTERPRISE_MEMBER_NAV_V18_2,
  PRIMARY_MEMBER_NAV_V18_2,
  UTILITY_MEMBER_NAV_V18_2,
} from "./navigationContractV18_2";

/** V18.2 simplified primary member navigation (總覽 / 掃描器 / 警報 / 情報). */
export const MEMBER_NAV = [...PRIMARY_MEMBER_NAV_V18_2] as const;

export const MEMBER_UTILITY_NAV = [...UTILITY_MEMBER_NAV_V18_2] as const;

export const MEMBER_ENTERPRISE_NAV = [...ENTERPRISE_MEMBER_NAV_V18_2] as const;

/** Deep links — not in primary nav; integrated under opportunity / research detail. */
export const MEMBER_DEEP_ROUTES = [
  { to: "/market", labelKey: "nav.market", shortKey: "nav.market.short" },
  { to: "/decisions", labelKey: "nav.decisions", shortKey: "nav.decisions.short" },
  { to: "/evidence", labelKey: "nav.evidence", shortKey: "nav.evidence.short" },
  {
    to: "/counter-evidence",
    labelKey: "nav.counterEvidence",
    shortKey: "nav.counterEvidence.short",
  },
  { to: "/risk-conditions", labelKey: "nav.risk", shortKey: "nav.risk.short" },
  { to: "/thesis-monitor", labelKey: "nav.thesis", shortKey: "nav.thesis.short" },
  { to: "/decision-memory", labelKey: "nav.memory", shortKey: "nav.memory.short" },
  { to: "/outcome-review", labelKey: "nav.outcome", shortKey: "nav.outcome.short" },
  { to: "/membership", labelKey: "nav.membership", shortKey: "nav.membership.short" },
] as const satisfies ReadonlyArray<{
  to: string;
  labelKey: MessageKey;
  shortKey: MessageKey;
}>;

assertMemberNavPathsClean(MEMBER_NAV.map((i) => i.to));
assertMemberNavPathsClean(MEMBER_UTILITY_NAV.map((i) => i.to));
if (countMemberExecutionControls(MEMBER_NAV.map((i) => i.to)) !== 0) {
  throw new Error("HARD BAN: member_execution_control_count must be 0");
}

export const MEMBER_ACCOUNT_SUBNAV = [
  { to: "/account", labelKey: "nav.account" },
  { to: "/privacy", labelKey: "nav.privacy" },
  { to: "/account-deletion", labelKey: "nav.accountDeletion" },
  { to: "/notification-settings", labelKey: "nav.notifications" },
] as const satisfies ReadonlyArray<{ to: string; labelKey: MessageKey }>;

/** Required page inventory for PUB-D acceptance (English identifiers). */
export const REQUIRED_MEMBER_PAGES = [
  "Home",
  "Scanner",
  "Alerts",
  "Intelligence",
  "Market Overview",
  "Decision Feed",
  "Decision Detail",
  "Evidence",
  "Counter Evidence",
  "Risk Conditions",
  "Thesis Monitor",
  "Alerts",
  "Decision Memory",
  "Outcome Review",
  "NEX AI Conversation",
  "Membership",
  "Account",
  "Privacy",
  "Account Deletion",
  "Notification Settings",
] as const;
