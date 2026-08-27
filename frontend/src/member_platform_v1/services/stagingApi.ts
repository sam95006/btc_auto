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
export async function stagingRegister(input: {
  displayName: string; email: string; password: string; confirmPassword: string; founderClaimCode?: string;
}) {
  return getJson<{ registered: true; role: "MEMBER" | "FOUNDER"; tier: "FREE" | "ENTERPRISE" }>("/member/registration", {
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
