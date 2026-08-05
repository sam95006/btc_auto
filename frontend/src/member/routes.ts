import type { MessageKey } from "../i18n";

/** Member Platform route inventory — labels resolved via i18n keys. */
export const MEMBER_NAV = [
  { to: "/home", labelKey: "nav.home", shortKey: "nav.home.short" },
  { to: "/market", labelKey: "nav.market", shortKey: "nav.market.short" },
  { to: "/intelligence", labelKey: "nav.intel", shortKey: "nav.intel.short" },
  { to: "/decisions", labelKey: "nav.decisions", shortKey: "nav.decisions.short" },
  { to: "/evidence", labelKey: "nav.evidence", shortKey: "nav.evidence.short" },
  {
    to: "/counter-evidence",
    labelKey: "nav.counterEvidence",
    shortKey: "nav.counterEvidence.short",
  },
  { to: "/risk-conditions", labelKey: "nav.risk", shortKey: "nav.risk.short" },
  { to: "/thesis-monitor", labelKey: "nav.thesis", shortKey: "nav.thesis.short" },
  { to: "/alerts", labelKey: "nav.alerts", shortKey: "nav.alerts.short" },
  { to: "/decision-memory", labelKey: "nav.memory", shortKey: "nav.memory.short" },
  { to: "/outcome-review", labelKey: "nav.outcome", shortKey: "nav.outcome.short" },
  { to: "/nex-ai", labelKey: "nav.nexAi", shortKey: "nav.nexAi.short" },
  { to: "/membership", labelKey: "nav.membership", shortKey: "nav.membership.short" },
  { to: "/account", labelKey: "nav.account", shortKey: "nav.account.short" },
] as const satisfies ReadonlyArray<{
  to: string;
  labelKey: MessageKey;
  shortKey: MessageKey;
}>;

export const MEMBER_ACCOUNT_SUBNAV = [
  { to: "/account", labelKey: "nav.account" },
  { to: "/privacy", labelKey: "nav.privacy" },
  { to: "/account-deletion", labelKey: "nav.accountDeletion" },
  { to: "/notification-settings", labelKey: "nav.notifications" },
] as const satisfies ReadonlyArray<{ to: string; labelKey: MessageKey }>;

/** Required page inventory for PUB-D acceptance (English identifiers). */
export const REQUIRED_MEMBER_PAGES = [
  "Home",
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
