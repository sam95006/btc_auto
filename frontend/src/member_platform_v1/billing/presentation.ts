// Presentation-only mapping for BILLING-5 member UI. This NEVER changes the
// backend stable entitlement/plan codes or authority — it only produces
// human-readable labels for display. Backend remains source of truth.

export const ENTITLEMENT_LABELS: Record<string, string> = {
  market_overview: "市場總覽",
  basic_market_data: "基礎市場資料",
  basic_alerts: "基礎提醒",
  market_intelligence: "市場情報",
  watchlists: "觀察清單",
  extended_market_history: "延伸歷史資料",
  advanced_signals: "進階訊號",
  risk_intelligence: "風險情報",
  advanced_analysis: "進階分析",
  report_generation: "報告產生",
  premium_intelligence: "頂級情報",
  higher_usage_limits: "更高用量上限",
  advanced_data: "進階數據",
  advanced_risk_analysis: "進階風險分析",
  organization_features: "組織功能",
  enterprise_agents: "企業代理",
  enterprise_data: "企業數據",
  enterprise_admin: "企業管理",
  custom_limits: "客製化上限",
};

export function entitlementLabel(code: string): string {
  return ENTITLEMENT_LABELS[code] || code;
}

// User-friendly subscription status text (raw enum kept only for debug/data).
export const STATUS_LABELS: Record<string, string> = {
  inactive: "免費 / 無有效訂閱",
  trialing: "試用中",
  active: "使用中",
  past_due: "付款出現問題",
  canceled: "已取消",
  expired: "已到期",
};

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] || status;
}

export const PLAN_TAGLINES: Record<string, string> = {
  free: "免費入門",
  starter: "起步方案",
  pro: "專業方案",
  advanced: "進階方案",
  enterprise: "企業方案",
};

export function planTagline(code: string): string {
  return PLAN_TAGLINES[code] || "";
}

// Plans that a member can self-service checkout. Enterprise is contact-sales;
// free is the default tier. Backend enforces this too.
export const SELF_SERVICE_PLANS = new Set(["starter", "pro", "advanced"]);

export function isSelfServicePlan(code: string): boolean {
  return SELF_SERVICE_PLANS.has(code);
}
