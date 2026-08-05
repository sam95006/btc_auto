export const VIEWPORTS = {
  desktop: { width: 1440, height: 900 },
  tablet: { width: 768, height: 1024 },
  mobile: { width: 390, height: 844 },
  /** WCAG / PUB2-J overflow gate */
  mobile375: { width: 375, height: 812 },
} as const;

/** Legacy wave4 routes (kept for older specs). */
export const PRIMARY_ROUTES = [
  { path: "/overview", heading: "總覽" },
  { path: "/universe", heading: "全市場" },
  { path: "/opportunities", heading: "機會" },
  { path: "/alerts", heading: "警報" },
  { path: "/portfolio", heading: "投資組合" },
  { path: "/learning", heading: "學習" },
  { path: "/evidence", heading: "Evidence Center" },
] as const;

/** Member Platform routes for PUB2-J a11y (zh-TW default headings). */
export const MEMBER_A11Y_ROUTES = [
  { path: "/home", headingZh: "NEXUS 會員首頁", headingEn: "NEXUS Member Home" },
  { path: "/market", headingZh: "市場總覽", headingEn: "Market Overview" },
  { path: "/decisions", headingZh: "決策動態", headingEn: "Decision Feed" },
  { path: "/evidence", headingZh: "證據", headingEn: "Evidence" },
  { path: "/counter-evidence", headingZh: "反證", headingEn: "Counter Evidence" },
  { path: "/risk-conditions", headingZh: "風險條件", headingEn: "Risk Conditions" },
  { path: "/thesis-monitor", headingZh: "論點監控", headingEn: "Thesis Monitor" },
  { path: "/alerts", headingZh: "警示", headingEn: "Alerts" },
  { path: "/decision-memory", headingZh: "決策記憶", headingEn: "Decision Memory" },
  { path: "/outcome-review", headingZh: "結果回顧", headingEn: "Outcome Review" },
  { path: "/nex-ai", headingZh: "NEX AI", headingEn: "NEX AI" },
  { path: "/membership", headingZh: "會員方案", headingEn: "Membership" },
  { path: "/account", headingZh: "帳戶", headingEn: "Account" },
  { path: "/privacy", headingZh: "隱私", headingEn: "Privacy" },
  { path: "/notification-settings", headingZh: "通知設定", headingEn: "Notification Settings" },
] as const;

export const ARTIFACTS_AFTER_DIR = "../../artifacts/wave4/after";
export const ARTIFACTS_BEFORE_DIR = "../../artifacts/wave4/before";
