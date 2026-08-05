/** Member Platform route inventory — visual IA aligned to product pages. */
export const MEMBER_NAV = [
  { to: "/home", label: "Home", short: "Home" },
  { to: "/market", label: "Market Overview", short: "Market" },
  { to: "/decisions", label: "Decision Feed", short: "Decisions" },
  { to: "/evidence", label: "Evidence", short: "Evidence" },
  { to: "/counter-evidence", label: "Counter Evidence", short: "Counter" },
  { to: "/risk-conditions", label: "Risk Conditions", short: "Risk" },
  { to: "/thesis-monitor", label: "Thesis Monitor", short: "Thesis" },
  { to: "/alerts", label: "Alerts", short: "Alerts" },
  { to: "/decision-memory", label: "Decision Memory", short: "Memory" },
  { to: "/outcome-review", label: "Outcome Review", short: "Outcome" },
  { to: "/nex-ai", label: "NEX AI", short: "NEX AI" },
  { to: "/membership", label: "Membership", short: "Member" },
  { to: "/account", label: "Account", short: "Account" },
] as const;

export const MEMBER_ACCOUNT_SUBNAV = [
  { to: "/account", label: "Account" },
  { to: "/privacy", label: "Privacy" },
  { to: "/account-deletion", label: "Account Deletion" },
  { to: "/notification-settings", label: "Notification Settings" },
] as const;

/** Required page inventory for PUB-D acceptance. */
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
