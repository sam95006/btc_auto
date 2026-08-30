/**
 * Staging-only API adapter. It intentionally maps only public, product-alpha
 * contracts that nexus-api-staging actually serves; market/AI/Shadow fixture
 * models remain fixtures until their own read-model contracts exist.
 */

const DEFAULT_ORIGIN = "https://nexus-api-staging.zeabur.app";
let csrfToken: string | null = null;

function origin(): string {
  const candidate = (import.meta.env.VITE_NEXUS_API_ORIGIN || DEFAULT_ORIGIN).trim().replace(/\/$/, "");
  if (!/^https:\/\/[a-z0-9.-]+$/i.test(candidate)) {
    throw new Error("invalid_staging_api_origin");
  }
  return candidate;
}

async function getJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method || "GET").toUpperCase();
  const headers: Record<string, string> = { Accept: "application/json", ...(init.headers as Record<string, string> || {}) };
  if (csrfToken && ["POST", "PUT", "PATCH", "DELETE"].includes(method) && !headers["X-Nexus-Session"]) {
    headers["X-Nexus-CSRF"] = csrfToken;
  }
  const response = await fetch(`${origin()}/api/v1${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  if (!response.ok) throw new Error(`staging_api_http_${response.status}`);
  const body = await response.json() as T & { csrf_token?: string };
  if (typeof body.csrf_token === "string" && body.csrf_token.length > 0) {
    csrfToken = body.csrf_token;
  }
  return body as T;
}

/** Fail-closed probe helper: never invents an allowed=true outcome. */
async function getJsonAllowFailClosed<T extends { allowed: boolean; reason?: string }>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${origin()}/api/v1${path}`, {
    ...init,
    headers: { Accept: "application/json", ...(init.headers || {}) },
    credentials: "include",
  });
  if (response.status === 401 || response.status === 403) {
    const body = (await response.json().catch(() => ({}))) as Partial<T>;
    return {
      allowed: false,
      reason: body.reason || (response.status === 401 ? "invalid_or_expired_session" : "forbidden"),
    } as T;
  }
  if (!response.ok) throw new Error(`staging_api_http_${response.status}`);
  return response.json() as Promise<T>;
}

export type StagingApiStatus = {
  health: "OK" | "UNAVAILABLE";
  readiness: boolean;
  capabilitiesOk: boolean;
  authFoundation: string;
  runtime: "UNAVAILABLE_NOT_BOUND";
};

export type LiveMarketTicker = {
  symbol: string;
  current_price: number | null;
  change_24h_percent: number | null;
  high_24h: number | null;
  low_24h: number | null;
  volume_24h: number | null;
  provider_timestamp: string | null;
  server_received_timestamp: string | null;
  freshness: "FRESH" | "STALE" | "DEGRADED" | "UNAVAILABLE";
  data_delayed: boolean;
};

export type LiveMarketSnapshot = {
  data_class: "LIVE_READ_ONLY";
  provider: string;
  read_only: true;
  execution_controls: false;
  poll_interval_sec: number;
  server_timestamp: string;
  symbols: LiveMarketTicker[];
  fallback: "none" | "last_known_value" | "unavailable";
};

export type LiveMarketCandle = {
  open_time_ms: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  close_time_ms: number;
};

export type LiveMarketHistory = {
  data_class: "LIVE_READ_ONLY";
  symbol: string;
  interval: string;
  freshness: "FRESH" | "STALE" | "DEGRADED" | "UNAVAILABLE";
  data_delayed: boolean;
  fallback: "none" | "last_known_value" | "unavailable";
  server_timestamp: string;
  candles: LiveMarketCandle[];
};

export async function getStagingApiStatus(): Promise<StagingApiStatus> {
  const [health, readiness, capabilities, auth] = await Promise.all([
    getJson<{ application?: { status?: string }; shadow_readonly?: { runtime_state?: string } }>("/product/health"),
    getJson<{ ready?: boolean }>("/product/readiness"),
    getJson<{ validation?: { ok?: boolean } }>("/product/capabilities"),
    getJson<{ status?: string }>("/product/auth/foundation"),
  ]);
  return {
    health: health.application?.status === "OK" ? "OK" : "UNAVAILABLE",
    readiness: readiness.ready === true,
    capabilitiesOk: capabilities.validation?.ok === true,
    authFoundation: auth.status || "UNAVAILABLE",
    // Runtime must remain explicit: no API-provided live runtime exists yet.
    runtime: health.shadow_readonly?.runtime_state === "UNAVAILABLE_NOT_BOUND"
      ? "UNAVAILABLE_NOT_BOUND"
      : "UNAVAILABLE_NOT_BOUND",
  };
}

/** Public market telemetry only. This has no account or execution surface. */
export async function getLiveMarketSnapshot(): Promise<LiveMarketSnapshot> {
  const response = await fetch(`${origin()}/api/v1/market/snapshot`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`live_market_http_${response.status}`);
  return response.json() as Promise<LiveMarketSnapshot>;
}

export async function getLiveMarketHistory(
  symbol: string,
  interval: string,
  limit = 60
): Promise<LiveMarketHistory> {
  const query = new URLSearchParams({ symbol, interval, limit: String(limit) });
  const response = await fetch(`${origin()}/api/v1/market/history?${query}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`live_market_history_http_${response.status}`);
  return response.json() as Promise<LiveMarketHistory>;
}

export type LiveMarketTelemetry = {
  classification: "LIVE_API";
  symbol: string;
  freshness: "LIVE" | "DATA_DELAYED" | "UNAVAILABLE";
  server_timestamp: string;
  [key: string]: unknown;
};

export type LiveMarketRanking = {
  classification: "LIVE_API";
  ranking_type: "gainers" | "losers" | "volume" | "volatility" | "liquidity";
  rows: LiveMarketTicker[];
  freshness: "LIVE" | "DATA_DELAYED" | "UNAVAILABLE";
  server_timestamp: string;
  runtime_ranking_available: false;
};

export type MemberProfile = {
  account_id: string;
  email: string;
  display_name: string;
  locale: string;
  timezone: string;
  privacy_preferences: Record<string, unknown>;
  version: number;
};

export async function getLiveMarketRankings(metric: LiveMarketRanking["ranking_type"] = "gainers") {
  return getJson<LiveMarketRanking>(`/market/rankings?metric=${metric}&limit=30`);
}
export async function getMarketDerivatives(symbol: string) {
  return getJson<LiveMarketTelemetry>(`/market/instruments/${encodeURIComponent(symbol)}/derivatives`);
}
export async function getMarketLiquidity(symbol: string) {
  return getJson<LiveMarketTelemetry>(`/market/instruments/${encodeURIComponent(symbol)}/liquidity`);
}
export async function getMarketInstruments() {
  return getJson<{ classification: "LIVE_API"; instruments: Array<{ symbol: string; status: string }> }>("/market/instruments");
}

export async function stagingLogin(email: string, password: string) {
  return getJson<{ email: string; staging_only: true }>("/member/session/login", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }),
  });
}
export type StagingRegisterResult = {
  registered: boolean;
  verification_required?: boolean;
  account_status?: "ACTIVE" | "PENDING_VERIFICATION" | "DISABLED";
  role?: "MEMBER" | "FOUNDER";
  plan?: string;
  tier?: string;
  csrf_token?: string;
};

/** Pure decision helper: does this registration outcome require email
 * verification (and therefore has no usable session yet)? */
export function registrationRequiresVerification(result: StagingRegisterResult): boolean {
  return Boolean(result.verification_required) || result.account_status === "PENDING_VERIFICATION";
}

export async function stagingRegister(input: {
  displayName: string; email: string; password: string; confirmPassword: string; founderClaimCode?: string;
}): Promise<StagingRegisterResult> {
  return getJson<StagingRegisterResult>("/member/registration", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      display_name: input.displayName,
      email: input.email,
      password: input.password,
      confirm_password: input.confirmPassword,
      founder_claim_code: input.founderClaimCode || undefined,
    }),
  });
}
export async function stagingLogout() {
  const result = await getJson<{ ok: boolean }>("/member/session/logout", { method: "POST" });
  csrfToken = null;
  return result;
}
export async function getMemberSession() {
  return getJson<{ session: { user_id: string; email: string; account_status: "ACTIVE" | "DISABLED" | "PENDING_VERIFICATION"; role: "MEMBER" | "FOUNDER_ADMIN"; plan: "BEGINNER" | "INTERMEDIATE" | "PRO" | "ENTERPRISE" }; profile: MemberProfile; csrf_token?: string }>("/member/session");
}
export async function getMemberProfile() {
  return getJson<{ classification: "LIVE_MEMBER_DB"; profile: MemberProfile }>("/member/profile");
}
export async function updateMemberProfile(profile: Partial<MemberProfile>, version: number) {
  return getJson<{ classification: "LIVE_MEMBER_DB"; profile: MemberProfile }>("/member/profile", {
    method: "PATCH", headers: { "Content-Type": "application/json", "If-Match": String(version) }, body: JSON.stringify(profile),
  });
}
export async function getMemberWatchlist() {
  return getJson<{ classification: "LIVE_MEMBER_DB"; symbols: string[] }>("/member/watchlist");
}
export async function changeMemberWatchlist(symbol: string, add: boolean) {
  return getJson<{ classification: "LIVE_MEMBER_DB"; symbols: string[] }>("/member/watchlist", {
    method: add ? "POST" : "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ symbol }),
  });
}
export async function getNotificationPreferences() {
  return getJson<{ classification: "LIVE_MEMBER_DB"; preferences: Record<string, unknown> }>("/member/notification-preferences");
}
export async function updateNotificationPreferences(preferences: Record<string, unknown>) {
  return getJson<{ classification: "LIVE_MEMBER_DB"; preferences: Record<string, unknown> }>("/member/notification-preferences", {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(preferences),
  });
}
export async function getMemberNotifications() {
  return getJson<{ classification: "LIVE_MEMBER_DB"; notifications: Array<{ id: string; category: "market" | "watchlist"; symbol: string | null; title: string; body: string; read: boolean; created_at: string }> }>("/member/notifications");
}
export async function markMemberNotificationRead(id: string) {
  return getJson<{ ok: boolean }>(`/member/notifications/${encodeURIComponent(id)}/read`, { method: "POST" });
}
export async function getMemberEntitlements() {
  return getJson<{ classification: "LIVE_MEMBER_DB"; entitlements: string[]; plan: "BEGINNER" | "INTERMEDIATE" | "PRO" | "ENTERPRISE"; features: string[]; effective_limits: { watchlist: number }; billing: "NOT_IMPLEMENTED" }>("/member/entitlements");
}

export async function checkEntitlement(sessionId: string, capabilityId: string) {
  // No public login route yet: without a real server session this must fail closed.
  return getJsonAllowFailClosed<{ allowed: boolean; reason?: string }>("/product/entitlement/check", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Nexus-Session": sessionId },
    body: JSON.stringify({ capability_id: capabilityId }),
  });
}

export async function getOrganizationPermissions(sessionId: string) {
  return getJsonAllowFailClosed<{ allowed: boolean; permissions?: string[]; reason?: string }>(
    "/product/organization/permissions",
    {
      headers: { "X-Nexus-Session": sessionId },
    }
  );
}

export const STAGING_API_ORIGIN = origin();

// ---------------------------------------------------------------------------
// Member email lifecycle: verification + password reset.
// These endpoints return a structured {ok, code, message} body even on 4xx
// (e.g. an invalid/expired token), so they read the body regardless of status
// instead of throwing. No raw token is ever logged by the client.
// ---------------------------------------------------------------------------

export type EmailActionResponse = {
  ok: boolean;
  code: string;
  message: string;
  sessions_revoked?: number;
  delivery_status?: string;
  email_provider_configured?: boolean;
};

async function postEmailAction(path: string, body: Record<string, unknown>): Promise<EmailActionResponse> {
  const response = await fetch(`${origin()}/api/v1${path}`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (response.status === 429) {
    return { ok: false, code: "rate_limited", message: "Too many requests. Please try again shortly." };
  }
  return (await response.json()) as EmailActionResponse;
}

export async function stagingVerifyEmail(token: string): Promise<EmailActionResponse> {
  return postEmailAction("/product/auth/verify-email", { token });
}

export async function stagingResendVerification(email: string): Promise<EmailActionResponse> {
  return postEmailAction("/product/auth/resend-verification", { email });
}

export async function stagingForgotPassword(email: string): Promise<EmailActionResponse> {
  return postEmailAction("/product/auth/forgot-password", { email });
}

export async function stagingResetPassword(token: string, newPassword: string): Promise<EmailActionResponse> {
  return postEmailAction("/product/auth/reset-password", { token, new_password: newPassword });
}

// ---------------------------------------------------------------------------
// Billing (BILLING-5). Backend is the sole source of truth for plan /
// subscription / entitlement state. The client only displays and initiates.
// ---------------------------------------------------------------------------

export type BillingPlan = {
  code: string;
  display_name: string;
  description: string;
  billing_interval: string | null;
  price_amount: number | null;
  currency: string | null;
  active: boolean;
  sort_order: number;
};

export type BillingSubscription = {
  account_id: string;
  plan_code: string;
  status: string;
  is_live: boolean;
  cancel_at_period_end: boolean;
  current_period_end: string | null;
  started_at: string | null;
  canceled_at: string | null;
  ended_at: string | null;
};

export type BillingEntitlements = {
  effective_plan_code: string;
  subscription_status: string;
  entitlements: string[];
};

export type BillingActionResult<T> = { ok: boolean; status: number; body: T | null };

export async function getBillingPlans(): Promise<{ plans: BillingPlan[]; default_plan_code: string }> {
  return getJson<{ plans: BillingPlan[]; default_plan_code: string }>("/billing/plans");
}

export async function getBillingSubscription(): Promise<{ subscription: BillingSubscription }> {
  return getJson<{ subscription: BillingSubscription }>("/billing/subscription");
}

export async function getBillingEntitlements(): Promise<BillingEntitlements> {
  return getJson<BillingEntitlements>("/billing/entitlements");
}

async function postBilling<T>(path: string, body?: object): Promise<BillingActionResult<T>> {
  const response = await fetch(`${origin()}/api/v1${path}`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    credentials: "include",
    body: body ? JSON.stringify(body) : undefined,
  });
  let parsed: T | null = null;
  try {
    parsed = (await response.json()) as T;
  } catch {
    parsed = null;
  }
  return { ok: response.ok, status: response.status, body: parsed };
}

export async function startBillingCheckout(
  planCode: string,
): Promise<BillingActionResult<{ checkout: { checkout_url: string | null; target_plan_code: string; status: string } }>> {
  // The server chooses the price and hosted checkout URL; the client only sends
  // the plan code.
  return postBilling("/billing/checkout", { plan_code: planCode });
}

export async function cancelBillingSubscription(): Promise<
  BillingActionResult<{ result: { status: string; cancel_at_period_end: boolean } }>
> {
  return postBilling("/billing/cancel");
}

export async function openBillingPortal(): Promise<
  BillingActionResult<{ portal: { portal_url: string | null } }>
> {
  return postBilling("/billing/portal");
}

export type BillingUsageQuota = {
  quota_code: string;
  label: string;
  quota_type: string;
  window: string;
  limit: number;
  used: number;
  remaining: number;
  reset_at: string | null;
};

export type BillingUsage = {
  effective_plan_code: string;
  quotas: BillingUsageQuota[];
};

export async function getBillingUsage(): Promise<BillingUsage> {
  return getJson<BillingUsage>("/billing/usage");
}

// ---------------------------------------------------------------------------
// Personal Market Intelligence product (PERSONAL-1). Every paid action is
// gated on the backend by Authentication AND Entitlement AND (when metered)
// Quota. The client only reflects the backend's authoritative decision; it
// never fabricates entitlement, market data, signals, or risk.
// ---------------------------------------------------------------------------

export type PersonalFeature = {
  key: string;
  label: string;
  entitlement: string;
  entitled: boolean;
  available: boolean;
  locked: boolean;
  quota_kind: "none" | "consumable" | "capacity";
  quota_code: string | null;
};

export type PersonalFeatures = {
  effective_plan_code: string;
  features: PersonalFeature[];
};

export type PersonalAnalysis = {
  data_class: "MEMBER_SAFE_ANALYSIS";
  symbol: string;
  points: number;
  trend: "up" | "down" | "flat";
  volatility: "high" | "moderate" | "low";
  change_pct: number;
  range_pct: number;
};

/** Member-safe provenance for real market-bound results (no secret fields). */
export type PersonalProvenance = {
  symbol?: string;
  interval?: string;
  provider?: string;
  source_class?: string;
  freshness?: string;
  data_timestamp?: string | null;
  analysis_timestamp?: string | null;
  points?: number;
};

export type PersonalReport = {
  data_class: "MEMBER_SAFE_REPORT";
  symbol: string;
  summary: string;
  sections: Array<{ title: string; value: unknown }>;
  provenance?: PersonalProvenance;
};

export type PersonalActionResult<T> = { ok: boolean; status: number; body: T | null };

export async function getPersonalFeatures(): Promise<PersonalFeatures> {
  return getJson<PersonalFeatures>("/personal/features");
}

async function postPersonal<T>(path: string, body?: object): Promise<PersonalActionResult<T>> {
  const response = await fetch(`${origin()}/api/v1${path}`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    credentials: "include",
    body: body ? JSON.stringify(body) : undefined,
  });
  let parsed: T | null = null;
  try {
    parsed = (await response.json()) as T;
  } catch {
    parsed = null;
  }
  return { ok: response.ok, status: response.status, body: parsed };
}

/** Stable idempotency key so a retried request never double-charges quota. */
export function newIdempotencyKey(prefix: string): string {
  const rand = Math.random().toString(36).slice(2, 10);
  return `${prefix}_${Date.now().toString(36)}_${rand}`;
}

export async function runPersonalAnalysis(
  symbol: string,
  idempotencyKey: string,
): Promise<PersonalActionResult<{ ok: boolean; analysis: PersonalAnalysis; provenance: PersonalProvenance; remaining: number }>> {
  return postPersonal("/personal/analysis", { symbol, idempotency_key: idempotencyKey });
}

export async function runPersonalReport(
  symbol: string,
  idempotencyKey: string,
): Promise<PersonalActionResult<{ ok: boolean; report: PersonalReport; remaining: number }>> {
  return postPersonal("/personal/report", { symbol, idempotency_key: idempotencyKey });
}

export async function getPersonalWatchlist(): Promise<{ symbols: string[]; used: number; capacity: number }> {
  return getJson<{ symbols: string[]; used: number; capacity: number }>("/personal/watchlist");
}

export async function addPersonalWatchlist(
  symbol: string,
): Promise<PersonalActionResult<{ ok: boolean; symbols: string[]; used: number; capacity: number }>> {
  return postPersonal("/personal/watchlist", { symbol });
}

export async function removePersonalWatchlist(
  symbol: string,
): Promise<PersonalActionResult<{ ok: boolean; symbols: string[] }>> {
  const response = await fetch(`${origin()}/api/v1/personal/watchlist/${encodeURIComponent(symbol)}`, {
    method: "DELETE",
    headers: { Accept: "application/json" },
    credentials: "include",
  });
  let parsed: { ok: boolean; symbols: string[] } | null = null;
  try {
    parsed = (await response.json()) as { ok: boolean; symbols: string[] };
  } catch {
    parsed = null;
  }
  return { ok: response.ok, status: response.status, body: parsed };
}

export type PersonalHistoryCandle = {
  open?: number;
  high?: number;
  low?: number;
  close?: number;
  volume?: number;
  close_time_ms?: number | null;
};

export type PersonalHistory = {
  symbol: string;
  requested_days: number;
  effective_days: number;
  clamped: boolean;
  max_days: number;
  provider_window_max: number;
  data_points: number;
  data: PersonalHistoryCandle[];
  freshness?: string;
  provider?: string;
  source_class?: string;
};

export async function getPersonalHistory(symbol: string, days: number): Promise<PersonalHistory> {
  const query = new URLSearchParams({ symbol, days: String(days) });
  return getJson<PersonalHistory>(`/personal/history?${query}`);
}

export type PersonalSignals = {
  data_class: "MEMBER_SAFE_SIGNALS";
  available: boolean;
  reason?: string;
  signals: unknown[];
};

export type PersonalRiskDescriptor = {
  data_class: "MEMBER_SAFE_RISK";
  symbol?: string;
  risk_level: "contained" | "moderate" | "elevated";
  volatility: string;
  range_pct: number;
  basis: string;
};

export type PersonalRisk = {
  data_class: "MEMBER_SAFE_RISK";
  available: boolean;
  reason?: string;
  risk?: PersonalRiskDescriptor;
  provenance?: PersonalProvenance;
};

export async function getPersonalSignals(): Promise<PersonalSignals> {
  return getJson<PersonalSignals>("/personal/signals");
}

export async function getPersonalRisk(symbol = "BTCUSDT"): Promise<PersonalRisk> {
  return getJson<PersonalRisk>(`/personal/risk?symbol=${encodeURIComponent(symbol)}`);
}

export type PersonalClosedBetaHealth = {
  data_class: "MEMBER_SAFE_HEALTH";
  overall: "healthy" | "degraded" | "unavailable";
  critical_unavailable: string[];
  dependencies: Record<string, { status: "ok" | "unavailable" | "unknown"; detail?: string }>;
};

export async function getPersonalClosedBetaHealth(): Promise<PersonalClosedBetaHealth> {
  return getJson<PersonalClosedBetaHealth>("/personal/closed-beta-health");
}
