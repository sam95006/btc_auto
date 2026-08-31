/**
 * Privacy-conscious, first-party analytics foundation. Sends a small, fixed set
 * of product events to the backend. NO fingerprinting, NO PII, NO cross-site
 * identifiers — just an allow-listed event name and an optional short label.
 * If the backend endpoint is unavailable, events are silently dropped (the
 * frontend never fabricates metrics; the admin Analytics view reads only what
 * the backend actually recorded).
 */
import { postAnalyticsEvent } from "../api/client";

export type AnalyticsEvent =
  | "page_view"
  | "cta_primary"
  | "cta_personal"
  | "cta_enterprise"
  | "personal_interest"
  | "enterprise_interest"
  | "contact_submit";

const ALLOWED: ReadonlySet<AnalyticsEvent> = new Set<AnalyticsEvent>([
  "page_view", "cta_primary", "cta_personal", "cta_enterprise",
  "personal_interest", "enterprise_interest", "contact_submit",
]);

export function track(event: AnalyticsEvent, label?: string): void {
  if (!ALLOWED.has(event)) return;
  // path is non-identifying; label is a short, caller-controlled string.
  const path = typeof location !== "undefined" ? location.pathname : "";
  void postAnalyticsEvent({ event, path, label: (label || "").slice(0, 64) }).catch(() => {});
}
