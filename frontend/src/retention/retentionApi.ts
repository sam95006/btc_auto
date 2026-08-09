/** Retention API client — server-authoritative; AUTH_REQUIRED_BLOCKER when unauthenticated. */

export const AUTH_REQUIRED_BLOCKER = "AUTH_REQUIRED_BLOCKER" as const;
export const RETENTION_MARKER = "PUBLIC_V18_2_20_PAID_BETA_RETENTION_HEAD" as const;

const BASE = "/api/nexus/public/retention";

export type RetentionAuthState = {
  token: string | null;
  accountId: string | null;
};

const TOKEN_KEY = "nexus.public.auth.token.v1";

export function loadRetentionAuth(): RetentionAuthState {
  try {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) return { token: null, accountId: null };
    return { token, accountId: null };
  } catch {
    return { token: null, accountId: null };
  }
}

export function saveRetentionToken(token: string | null) {
  try {
    if (!token) localStorage.removeItem(TOKEN_KEY);
    else localStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* ignore */
  }
}

async function retentionFetch(path: string, init: RequestInit = {}) {
  const auth = loadRetentionAuth();
  const headers = new Headers(init.headers || {});
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (auth.token) headers.set("Authorization", `Bearer ${auth.token}`);
  const res = await fetch(`${BASE}${path}`, { ...init, headers, cache: "no-store" });
  const body = await res.json().catch(() => ({}));
  return { res, body };
}

export function isAuthRequired(body: unknown): boolean {
  const b = body as { error?: string; blocker?: string };
  return b?.error === AUTH_REQUIRED_BLOCKER || b?.blocker === AUTH_REQUIRED_BLOCKER;
}

export async function fetchRetentionFoundation() {
  const { body } = await retentionFetch("/foundation");
  return body;
}

export async function fetchServerWatchlist() {
  return retentionFetch("/watchlist");
}

export async function addServerWatch(symbol: string, assetClass = "CRYPTO") {
  return retentionFetch("/watchlist/add", {
    method: "POST",
    body: JSON.stringify({ symbol, asset_class: assetClass }),
  });
}

export async function removeServerWatch(symbol: string, assetClass = "CRYPTO") {
  return retentionFetch("/watchlist/remove", {
    method: "POST",
    body: JSON.stringify({ symbol, asset_class: assetClass }),
  });
}

export async function fetchNotifications(limit = 40) {
  return retentionFetch(`/notifications?limit=${limit}`);
}

export async function markNotificationRead(id: string) {
  return retentionFetch("/notifications/read", {
    method: "POST",
    body: JSON.stringify({ id }),
  });
}

export async function fetchSinceLastVisit() {
  return retentionFetch("/since-last-visit");
}

export async function fetchOnboarding() {
  return retentionFetch("/onboarding");
}

export async function completeOnboardingStep(stepId: string) {
  return retentionFetch("/onboarding/step", {
    method: "POST",
    body: JSON.stringify({ step_id: stepId }),
  });
}

export async function dismissOnboarding() {
  return retentionFetch("/onboarding/dismiss", { method: "POST", body: "{}" });
}
