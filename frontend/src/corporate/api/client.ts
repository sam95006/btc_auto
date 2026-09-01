// Corporate API client. Talks only to the public Core/Corporate API. Contains
// NO secrets — only a public API origin from build config. It never imports
// Founder/private-trading code.

import type {
  AdminSession,
  ContentEnvelope,
  EventsFeed,
  HomeContent,
  MarketBrief,
  MarketHistory,
  MarketShowcase,
  SiteContent,
} from "../types";

const DEFAULT_ORIGIN = "https://nexus-api-staging.zeabur.app";

function origin(): string {
  const candidate = (import.meta.env.VITE_NEXUS_API_ORIGIN || DEFAULT_ORIGIN).trim().replace(/\/$/, "");
  if (!/^https:\/\/[a-z0-9.-]+$/i.test(candidate)) throw new Error("invalid_corporate_api_origin");
  return candidate;
}

/** Public API origin (for EventSource / direct URLs). */
export const API_ORIGIN = origin();

/** Append ?locale=… (or &locale=…) when a locale is provided. */
function withLocale(path: string, locale?: string): string {
  if (!locale) return path;
  return `${path}${path.includes("?") ? "&" : "?"}locale=${encodeURIComponent(locale)}`;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${origin()}${path}`, { headers: { Accept: "application/json" } });
  if (!res.ok && res.status !== 404) throw new Error(`corporate_api_http_${res.status}`);
  return (await res.json()) as T;
}

// CSRF for admin mutations. The readable double-submit cookie (corp_csrf) is
// host-scoped to the API origin, so on a cross-origin deployment (Corporate
// frontend on a different subdomain than the Core API) it is NOT visible to
// document.cookie here. We therefore keep the token in memory, captured from the
// login/owner-setup/session responses, and fall back to the cookie for
// same-origin deployments. The token itself is never persisted to storage.
let csrfToken = "";

function rememberCsrf(body: unknown): void {
  const t = (body as { csrf_token?: unknown } | null)?.csrf_token;
  if (typeof t === "string" && t) csrfToken = t;
}

function csrfFromCookie(): string {
  if (typeof document === "undefined") return "";
  const m = document.cookie.match(/(?:^|;\s*)corp_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

// ---- public content (locale-aware) ----
export const getSite = (locale?: string) => getJson<ContentEnvelope<SiteContent>>(withLocale("/api/corporate/v1/site", locale));
export const getHome = (locale?: string) => getJson<ContentEnvelope<HomeContent>>(withLocale("/api/corporate/v1/home", locale));
export const getContent = <T = Record<string, unknown>>(slug: string, locale?: string) =>
  getJson<ContentEnvelope<T>>(withLocale(`/api/corporate/v1/content/${slug}`, locale));
export const getMarket = (locale?: string) => getJson<MarketShowcase>(withLocale("/api/corporate/v1/market", locale));
export const getStatus = () => getJson<Record<string, unknown>>("/api/corporate/v1/status");
export const getLocales = () => getJson<{ supported: string[]; default: string }>("/api/corporate/v1/locales");
export const getHistory = (symbol: string, interval = "1h", limit = 48) =>
  getJson<MarketHistory>(`/api/corporate/v1/history/${symbol}?interval=${interval}&limit=${limit}`);
export const getEvents = (locale?: string) => getJson<EventsFeed>(withLocale("/api/corporate/v1/events", locale));
export const getBrief = (locale?: string) => getJson<MarketBrief>(withLocale("/api/corporate/v1/brief", locale));

export async function submitContact(input: { name?: string; email: string; company?: string; message?: string }) {
  const res = await fetch(`${origin()}/api/corporate/v1/contact`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return { ok: res.ok, status: res.status, body: (await res.json().catch(() => ({}))) as Record<string, unknown> };
}

// ---- owner bootstrap + admin ----
// The session is a server-managed HttpOnly cookie — never stored in JS/
// localStorage. Requests use credentials:"include"; mutations echo the CSRF
// cookie as a double-submit header.
async function adminFetch(path: string, init: RequestInit = {}) {
  const method = (init.method || "GET").toUpperCase();
  const headers: Record<string, string> = { Accept: "application/json", ...(init.headers as Record<string, string>) };
  if (["POST", "PUT", "DELETE", "PATCH"].includes(method)) headers["X-Corp-CSRF"] = csrfToken || csrfFromCookie();
  const res = await fetch(`${origin()}${path}`, { ...init, headers, credentials: "include" });
  const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  // Capture/refresh the CSRF token from any response that carries it (login,
  // owner-setup, and /admin/session), so mutations work after a reload too.
  rememberCsrf(body);
  return { ok: res.ok, status: res.status, body };
}

export const ownerSetup = (input: { email: string; password: string; display_name?: string }) =>
  adminFetch("/owner/setup", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) });

export const adminLogin = (email: string, password: string) =>
  adminFetch("/admin/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });

export const adminLogout = () =>
  adminFetch("/admin/logout", { method: "POST" }).then((r) => {
    csrfToken = "";
    return r;
  });

export const adminSession = () => adminFetch("/admin/session").then((r) => (r.ok ? (r.body as unknown as AdminSession) : { authenticated: false }));
export const adminContentList = () => adminFetch("/admin/content");
export const adminGetContent = (slug: string) => adminFetch(`/admin/content/${slug}`);
export const adminSaveContent = (slug: string, data: Record<string, unknown>) =>
  adminFetch(`/admin/content/${slug}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ data }) });
export const adminPublish = (slug: string) => adminFetch(`/admin/content/${slug}/publish`, { method: "POST" });
export const adminLeads = () => adminFetch("/admin/leads");
export const adminAudit = () => adminFetch("/admin/audit");
export const adminOverview = () => adminFetch("/admin/overview");
export const adminAnalytics = () => adminFetch("/admin/analytics");
export const adminCreateAdmin = (input: { email: string; password: string; display_name?: string; role?: string }) =>
  adminFetch("/admin/admins", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) });
// Authenticated draft preview — returns the DRAFT body shaped like the public
// content envelope so the same site components can render it. Never public.
export const adminPreview = (slug: string) => adminFetch(`/admin/preview/${slug}`);
export const adminGetSetting = (key: string) => adminFetch(`/admin/settings/${key}`);
export const adminSetSetting = (key: string, value: Record<string, unknown>) =>
  adminFetch(`/admin/settings/${key}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ value }) });

// ---- privacy-conscious first-party analytics (no PII, allow-listed events) ----
export async function postAnalyticsEvent(input: { event: string; path?: string; label?: string }) {
  const res = await fetch(`${origin()}/api/corporate/v1/analytics/event`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
    keepalive: true,
  });
  return { ok: res.ok, status: res.status };
}
