// Corporate API client. Talks only to the public Core/Corporate API. Contains
// NO secrets — only a public API origin from build config. It never imports
// Founder/private-trading code.

import type {
  AdminSession,
  ContentEnvelope,
  HomeContent,
  MarketShowcase,
  SiteContent,
} from "../types";

const DEFAULT_ORIGIN = "https://nexus-api-staging.zeabur.app";

function origin(): string {
  const candidate = (import.meta.env.VITE_NEXUS_API_ORIGIN || DEFAULT_ORIGIN).trim().replace(/\/$/, "");
  if (!/^https:\/\/[a-z0-9.-]+$/i.test(candidate)) throw new Error("invalid_corporate_api_origin");
  return candidate;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${origin()}${path}`, { headers: { Accept: "application/json" } });
  if (!res.ok && res.status !== 404) throw new Error(`corporate_api_http_${res.status}`);
  return (await res.json()) as T;
}

// CSRF for admin mutations: read the readable double-submit cookie the server
// set alongside the HttpOnly session cookie. The session token itself is never
// accessible to JS.
function csrfFromCookie(): string {
  if (typeof document === "undefined") return "";
  const m = document.cookie.match(/(?:^|;\s*)corp_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

// ---- public content ----
export const getSite = () => getJson<ContentEnvelope<SiteContent>>("/api/corporate/v1/site");
export const getHome = () => getJson<ContentEnvelope<HomeContent>>("/api/corporate/v1/home");
export const getContent = <T = Record<string, unknown>>(slug: string) =>
  getJson<ContentEnvelope<T>>(`/api/corporate/v1/content/${slug}`);
export const getMarket = () => getJson<MarketShowcase>("/api/corporate/v1/market");
export const getStatus = () => getJson<Record<string, unknown>>("/api/corporate/v1/status");

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
  if (["POST", "PUT", "DELETE", "PATCH"].includes(method)) headers["X-Corp-CSRF"] = csrfFromCookie();
  const res = await fetch(`${origin()}${path}`, { ...init, headers, credentials: "include" });
  return { ok: res.ok, status: res.status, body: (await res.json().catch(() => ({}))) as Record<string, unknown> };
}

export const ownerSetup = (input: { email: string; password: string; display_name?: string }) =>
  adminFetch("/owner/setup", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) });

export const adminLogin = (email: string, password: string) =>
  adminFetch("/admin/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });

export const adminLogout = () => adminFetch("/admin/logout", { method: "POST" });

export const adminSession = () => adminFetch("/admin/session").then((r) => (r.ok ? (r.body as unknown as AdminSession) : { authenticated: false }));
export const adminContentList = () => adminFetch("/admin/content");
export const adminGetContent = (slug: string) => adminFetch(`/admin/content/${slug}`);
export const adminSaveContent = (slug: string, data: Record<string, unknown>) =>
  adminFetch(`/admin/content/${slug}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ data }) });
export const adminPublish = (slug: string) => adminFetch(`/admin/content/${slug}/publish`, { method: "POST" });
export const adminLeads = () => adminFetch("/admin/leads");
export const adminAudit = () => adminFetch("/admin/audit");
export const adminOverview = () => adminFetch("/admin/overview");
