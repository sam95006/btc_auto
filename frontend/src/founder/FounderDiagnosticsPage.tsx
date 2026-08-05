import { useEffect, useState } from "react";
import {
  fetchFounderDiagnostics,
  postResearchAuthorize,
} from "./api";
import type {
  FounderDiagnosticsSnapshot,
  FounderOperatorPanel,
  ResearchAuthorizeResult,
} from "./types";
import { FOUNDER_DIAGNOSTICS_NAV } from "./types";

function healthClass(health: string): string {
  const h = health.toUpperCase();
  if (h === "OK" || h === "ARMED_READINESS") return "ok";
  if (h.includes("BLOCK") || h.includes("FAIL")) return "bad";
  return "warn";
}

function MetricValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <>—</>;
  if (typeof value === "object") {
    return <pre className="mono sm nx-founder-json">{JSON.stringify(value, null, 2)}</pre>;
  }
  return <>{String(value)}</>;
}

function PanelCard({ panel }: { panel: FounderOperatorPanel }) {
  const metrics = Object.entries(panel.metrics || {});
  const binding = panel.binding;
  return (
    <section className="nx-card nx-founder-panel" id={panel.id} aria-label={panel.title}>
      <div className="nx-founder-panel-head">
        <h2>{panel.title}</h2>
        <span className={`tag tag-${healthClass(panel.health)}`}>{panel.health}</span>
      </div>
      <p className="muted sm">{panel.summary}</p>
      {binding ? (
        <div className="nx-founder-binding" aria-label="Surface binding">
          <span className={`tag tag-${binding.mode === "LIVE" ? "ok" : "warn"}`}>
            bind={binding.mode}
          </span>
          <span className="muted sm mono">{binding.sourceSurface}</span>
        </div>
      ) : null}
      <dl className="nx-founder-metrics">
        {metrics.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd className="mono">
              <MetricValue value={v} />
            </dd>
          </div>
        ))}
      </dl>
      {panel.notes?.length ? (
        <ul className="nx-founder-notes muted sm">
          {panel.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      ) : null}
      <div className="tag">read-only · researchOnly · memberVisible=false</div>
    </section>
  );
}

/**
 * UX-C Founder Operator Diagnostics — V16 research observe panels.
 * Observe / authorize research only. Never mainnet / real-trade.
 */
export function FounderDiagnosticsPage() {
  const [snap, setSnap] = useState<FounderDiagnosticsSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [authResult, setAuthResult] = useState<ResearchAuthorizeResult | null>(null);
  const [authBusy, setAuthBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const result = await fetchFounderDiagnostics();
      if (cancelled) return;
      setLoading(false);
      if (!result.ok) {
        setError(("error" in result && result.error) || "diagnostics_denied");
        setSnap(null);
        return;
      }
      setSnap(result as FounderDiagnosticsSnapshot);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function onAuthorizeResearch() {
    setAuthBusy(true);
    const result = await postResearchAuthorize("observe_diagnostics");
    setAuthResult(result);
    setAuthBusy(false);
  }

  if (loading) {
    return (
      <div className="page-stack nx-founder-operator">
        <p className="muted">載入 Founder Diagnostics…</p>
      </div>
    );
  }

  if (error || !snap) {
    return (
      <div className="page-stack nx-founder-operator" role="alert">
        <h1>Diagnostics Access Denied</h1>
        <p className="muted">會員工作階段無法讀取私有診斷資料（403 fail-closed）。</p>
        <div className="tag tag-warn">{error || "denied"}</div>
      </div>
    );
  }

  return (
    <div className="page-stack nx-founder-operator">
      <header>
        <h1>Founder Operator Diagnostics</h1>
        <p className="muted">
          UX-C · V16 research observe · {snap.actor.tier} · {snap.actor.identitySource} ·{" "}
          {snap.generatedAt}
        </p>
        <div className="nx-founder-banner-row">
          <span className="tag tag-warn">founder-only</span>
          <span className="tag">researchOnly={String(snap.researchOnly)}</span>
          <span className="tag">observeOnly={String(snap.observeOnly)}</span>
          <span className="tag">exchangeWrite={String(snap.exchangeWriteEnabled)}</span>
          <span className="tag">mainnetShortcut={String(snap.mainnetShortcut)}</span>
          <span className="tag">memberAccessible={String(snap.memberAccessible)}</span>
        </div>
      </header>

      <section className="nx-card" aria-label="Research authorize">
        <h2 className="sm">Authorize research observe</h2>
        <p className="muted sm">
          僅授權研究觀測／計畫 — 永不啟用 mainnet 或真實下單捷徑。
        </p>
        <button
          type="button"
          className="nx-founder-auth-btn"
          disabled={authBusy}
          onClick={() => void onAuthorizeResearch()}
        >
          {authBusy ? "授權中…" : "Authorize observe_diagnostics"}
        </button>
        {authResult ? (
          <div className="nx-founder-banner-row" style={{ marginTop: "0.5rem" }}>
            <span className={`tag tag-${authResult.authorized ? "ok" : "bad"}`}>
              authorized={String(authResult.authorized)}
            </span>
            <span className="tag">scope={authResult.scope}</span>
            <span className="tag">
              realExecution={String(authResult.realExecutionEnabled ?? false)}
            </span>
            {authResult.error ? <span className="tag tag-warn">{authResult.error}</span> : null}
          </div>
        ) : null}
      </section>

      <section className="nx-card" aria-label="Hard bans">
        <h2 className="sm">Hard bans (diagnostics)</h2>
        <div className="nx-founder-ban-chips">
          {snap.hardBans.map((b) => (
            <span key={b} className="tag">
              {b}
            </span>
          ))}
        </div>
      </section>

      <nav className="nx-founder-jump" aria-label="Diagnostics panels">
        {FOUNDER_DIAGNOSTICS_NAV.map((item) => (
          <a key={item.id} href={item.hash}>
            {item.label}
          </a>
        ))}
      </nav>

      <div className="nx-founder-panel-grid">
        {snap.panels.map((panel) => (
          <PanelCard key={panel.id} panel={panel} />
        ))}
      </div>
    </div>
  );
}
