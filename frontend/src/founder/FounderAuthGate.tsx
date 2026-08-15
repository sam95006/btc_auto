import { useEffect, useState, type ReactNode } from "react";
import { fetchFounderStatus } from "./api";
import type { FounderStatus } from "./types";

type GateState =
  | { phase: "loading" }
  | { phase: "denied"; reason: string }
  | { phase: "authorized"; status: FounderStatus };

/**
 * Private Founder authorization gate.
 * Member sessions always land on denied — no private panels render.
 */
export function FounderAuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<GateState>({ phase: "loading" });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const status = await fetchFounderStatus();
      if (cancelled) return;
      if (!status.ok || status.memberAccessible === true) {
        setState({
          phase: "denied",
          reason: status.error || "founder_authorization_required",
        });
        return;
      }
      if (status.founderOnly !== true && status.operatorUiEnabled !== true) {
        setState({ phase: "denied", reason: status.error || "founder_only" });
        return;
      }
      setState({ phase: "authorized", status });
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.phase === "loading") {
    return (
      <div className="page-stack nx-founder-gate" role="status">
        <p className="muted">驗證 Founder 授權中…</p>
      </div>
    );
  }

  if (state.phase === "denied") {
    const reason =
      state.reason === "Session unavailable" ||
      state.reason === "Permission denied" ||
      state.reason === "Founder access required" ||
      state.reason === "Runtime not bound"
        ? state.reason
        : "Founder access required";
    return (
      <div className="page-stack nx-founder-gate nx-founder-gate-denied" role="alert" data-classification="AUTH_REQUIRED">
        <header>
          <h1>Founder access required</h1>
          <p className="muted">此為 Founder 私有營運介面，會員工作階段無法存取。</p>
          <div className="tag tag-warn">AUTH_REQUIRED · founder-only</div>
        </header>
        <section className="nx-card">
          <p className="sm muted">{reason}</p>
          <p className="sm muted">
            Client headers / query / localStorage 無法提升為 Founder。診斷細節僅保留在後端日誌。
          </p>
        </section>
      </div>
    );
  }

  return <>{children}</>;
}
