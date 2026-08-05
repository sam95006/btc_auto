import type {
  FounderDiagnosticsSnapshot,
  FounderOperatorSnapshot,
  FounderStatus,
  ResearchAuthorizeResult,
} from "./types";

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

export async function fetchFounderDiagnostics(): Promise<
  FounderDiagnosticsSnapshot | { ok: false; error: string }
> {
  try {
    const res = await fetch("/api/nexus/founder/diagnostics", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const body = (await res.json()) as FounderDiagnosticsSnapshot & { error?: string };
    if (!res.ok) {
      return { ok: false, error: body.error || `http_${res.status}` };
    }
    return body;
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "network_error" };
  }
}

/** Research observe authorization only — never requests mainnet / real-trade scopes. */
export async function postResearchAuthorize(
  scope: string = "observe_diagnostics",
): Promise<ResearchAuthorizeResult> {
  try {
    const res = await fetch("/api/nexus/founder/diagnostics/research-authorize", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      cache: "no-store",
      body: JSON.stringify({ researchOnly: true, scope }),
    });
    const body = (await res.json()) as ResearchAuthorizeResult;
    if (!res.ok) {
      return {
        ok: false,
        authorized: false,
        scope,
        error: body.error || `http_${res.status}`,
        researchOnly: true,
        realExecutionEnabled: false,
        memberAccessible: false,
      };
    }
    return body;
  } catch (err) {
    return {
      ok: false,
      authorized: false,
      scope,
      error: err instanceof Error ? err.message : "network_error",
      researchOnly: true,
      realExecutionEnabled: false,
      memberAccessible: false,
    };
  }
}
