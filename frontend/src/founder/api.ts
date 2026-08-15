import type {
  FounderDemoMonitorSnapshot,
  FounderDiagnosticsSnapshot,
  FounderLiveOpsControlResult,
  FounderLiveOpsSnapshot,
  FounderOperatorSnapshot,
  FounderStatus,
  ResearchAuthorizeResult,
} from "./types";

/**
 * Founder private API client.
 * Never invents Founder identity client-side — server is sole authority.
 * Never exposes raw JSON/parser/HTML body errors to the UI.
 */
function sanitizeFounderError(status: number, raw?: string): string {
  const text = (raw || "").toLowerCase();
  if (status === 401) return "Session unavailable";
  if (status === 403) return "Permission denied";
  if (status === 404 || text.includes("unexpected token") || text.includes("<!doctype") || text.includes("syntaxerror")) {
    return "Founder access required";
  }
  if (text.includes("network") || text.includes("failed to fetch")) return "Session unavailable";
  return "Founder access required";
}

async function readFounderJson<T extends { error?: string }>(
  res: Response
): Promise<{ ok: true; body: T } | { ok: false; error: string }> {
  const contentType = res.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    return { ok: false, error: sanitizeFounderError(res.status) };
  }
  try {
    const body = (await res.json()) as T;
    return { ok: true, body };
  } catch {
    return { ok: false, error: sanitizeFounderError(res.status) };
  }
}

export async function fetchFounderStatus(): Promise<FounderStatus> {
  try {
    const res = await fetch("/api/nexus/founder/status", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const parsed = await readFounderJson<FounderStatus>(res);
    if (!parsed.ok) {
      return { ok: false, error: parsed.error, memberAccessible: false };
    }
    if (!res.ok) {
      return {
        ok: false,
        error: sanitizeFounderError(res.status, parsed.body.error),
        memberAccessible: false,
      };
    }
    return parsed.body;
  } catch {
    return { ok: false, error: "Session unavailable", memberAccessible: false };
  }
}

export async function fetchFounderOperatorSnapshot(): Promise<FounderOperatorSnapshot | { ok: false; error: string }> {
  try {
    const res = await fetch("/api/nexus/founder/operator", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const parsed = await readFounderJson<FounderOperatorSnapshot & { error?: string }>(res);
    if (!parsed.ok) return { ok: false, error: parsed.error };
    if (!res.ok) return { ok: false, error: sanitizeFounderError(res.status, parsed.body.error) };
    return parsed.body;
  } catch {
    return { ok: false, error: "Session unavailable" };
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
    const parsed = await readFounderJson<FounderDiagnosticsSnapshot & { error?: string }>(res);
    if (!parsed.ok) return { ok: false, error: parsed.error };
    if (!res.ok) return { ok: false, error: sanitizeFounderError(res.status, parsed.body.error) };
    return parsed.body;
  } catch {
    return { ok: false, error: "Session unavailable" };
  }
}

export async function fetchFounderLiveOps(): Promise<
  FounderLiveOpsSnapshot | { ok: false; error: string }
> {
  try {
    const res = await fetch("/api/nexus/founder/live-ops", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const parsed = await readFounderJson<FounderLiveOpsSnapshot & { error?: string }>(res);
    if (!parsed.ok) return { ok: false, error: parsed.error };
    if (!res.ok) return { ok: false, error: sanitizeFounderError(res.status, parsed.body.error) };
    return parsed.body;
  } catch {
    return { ok: false, error: "Session unavailable" };
  }
}

/** V18.2.25 Founder-only demo monitor — never invents PnL; empty when feed not ready. */
export async function fetchFounderDemoMonitor(): Promise<
  FounderDemoMonitorSnapshot | { ok: false; error: string; memberAccessible?: boolean }
> {
  try {
    const res = await fetch("/api/nexus/founder/demo-monitor", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const parsed = await readFounderJson<FounderDemoMonitorSnapshot & { error?: string }>(res);
    if (!parsed.ok) {
      return { ok: false, error: parsed.error, memberAccessible: false };
    }
    if (!res.ok) {
      return {
        ok: false,
        error: sanitizeFounderError(res.status, parsed.body.error),
        memberAccessible: false,
      };
    }
    return parsed.body;
  } catch {
    return { ok: false, error: "Session unavailable", memberAccessible: false };
  }
}

/** Allowed live-ops controls only — never trade/risk/leverage/mainnet. */
export async function postFounderLiveOpsControl(
  control: string,
  params?: Record<string, string>,
): Promise<FounderLiveOpsControlResult> {
  try {
    const res = await fetch("/api/nexus/founder/live-ops/control", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      cache: "no-store",
      body: JSON.stringify({ control, params: params || {} }),
    });
    const body = (await res.json()) as FounderLiveOpsControlResult;
    if (!res.ok) {
      return {
        ok: false,
        applied: false,
        control,
        error: sanitizeFounderError(res.status, body.error),
        banned: body.banned,
        exchangeWriteEnabled: false,
        mainnetShortcut: false,
        realExecutionEnabled: false,
        founderOnly: true,
        memberAccessible: false,
        banned_control_count: 0,
      };
    }
    return body;
  } catch (err) {
    return {
      ok: false,
      applied: false,
      control,
      error: "Session unavailable",
      exchangeWriteEnabled: false,
      founderOnly: true,
      memberAccessible: false,
      banned_control_count: 0,
    };
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
        error: sanitizeFounderError(res.status, body.error),
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
      error: "Session unavailable",
      researchOnly: true,
      realExecutionEnabled: false,
      memberAccessible: false,
    };
  }
}
