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

export async function fetchFounderLiveOps(): Promise<
  FounderLiveOpsSnapshot | { ok: false; error: string }
> {
  try {
    const res = await fetch("/api/nexus/founder/live-ops", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const body = (await res.json()) as FounderLiveOpsSnapshot & { error?: string };
    if (!res.ok) {
      return { ok: false, error: body.error || `http_${res.status}` };
    }
    return body;
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "network_error" };
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
    const body = (await res.json()) as FounderDemoMonitorSnapshot & { error?: string };
    if (!res.ok) {
      return {
        ok: false,
        error: body.error || `http_${res.status}`,
        memberAccessible: false,
      };
    }
    return body;
  } catch (err) {
    return {
      ok: false,
      error: err instanceof Error ? err.message : "network_error",
      memberAccessible: false,
    };
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
        error: body.error || `http_${res.status}`,
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
      error: err instanceof Error ? err.message : "network_error",
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
