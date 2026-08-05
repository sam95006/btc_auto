import type { FounderOperatorSnapshot, FounderStatus } from "./types";

/**
 * Founder private API client.
 * Never invents Founder identity client-side — server is sole authority.
 */
export async function fetchFounderStatus(): Promise<FounderStatus> {
  try {
    const res = await fetch("/api/nexus/founder/status", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const body = (await res.json()) as FounderStatus;
    if (!res.ok) {
      return { ok: false, error: body.error || `http_${res.status}`, memberAccessible: false };
    }
    return body;
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "network_error", memberAccessible: false };
  }
}

export async function fetchFounderOperatorSnapshot(): Promise<FounderOperatorSnapshot | { ok: false; error: string }> {
  try {
    const res = await fetch("/api/nexus/founder/operator", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const body = (await res.json()) as FounderOperatorSnapshot & { error?: string };
    if (!res.ok) {
      return { ok: false, error: body.error || `http_${res.status}` };
    }
    return body;
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "network_error" };
  }
}
