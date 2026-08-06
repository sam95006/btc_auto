import { useCallback, useEffect, useState } from "react";
import {
  fetchFounderLiveOps,
  postFounderLiveOpsControl,
} from "./api";
import type {
  FounderLiveOpsControlResult,
  FounderLiveOpsSnapshot,
  FounderOperatorPanel,
} from "./types";
import { FOUNDER_LIVE_OPS_NAV } from "./types";

function healthClass(health: string): string {
  const h = health.toUpperCase();
  if (h === "OK" || h === "RUNNING" || h === "STANDBY") return "ok";
  if (h.includes("ACTIVE") || h.includes("PAUSED") || h.includes("DEGRAD") || h.includes("WARN")) {
    return "warn";
  }
  if (h.includes("FAIL") || h.includes("BLOCK")) return "bad";
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
  return (
    <section className="nx-card nx-founder-panel" id={panel.id} aria-label={panel.title}>
      <div className="nx-founder-panel-head">
        <h2>{panel.title}</h2>
        <span className={`tag tag-${healthClass(panel.health)}`}>{panel.health}</span>
      </div>
      <p className="muted sm">{panel.summary}</p>
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
      <div className="tag">founder-only · banned_control_count=0 · no trade/risk/leverage/mainnet</div>
    </section>
  );
}

/**
 * PUB18-C Founder Live Operations.
 * Allowed controls only: pause/resume ingest, disable provider/source,
 * force read-only degraded, export evidence.
 */
export function FounderLiveOpsPage() {
  const [snap, setSnap] = useState<FounderLiveOpsSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [controlResult, setControlResult] = useState<FounderLiveOpsControlResult | null>(null);
  const [providerId, setProviderId] = useState("primary_chat");
  const [sourceId, setSourceId] = useState("bybit_public_v5");

  const reload = useCallback(async () => {
    const result = await fetchFounderLiveOps();
    if (!result.ok) {
      setError(("error" in result && result.error) || "live_ops_denied");
      setSnap(null);
      return;
    }
    setError(null);
    setSnap(result as FounderLiveOpsSnapshot);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const result = await fetchFounderLiveOps();
      if (cancelled) return;
      setLoading(false);
      if (!result.ok) {
        setError(("error" in result && result.error) || "live_ops_denied");
        setSnap(null);
        return;
      }
      setSnap(result as FounderLiveOpsSnapshot);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function runControl(control: string, params?: Record<string, string>) {
    setBusy(true);
    const result = await postFounderLiveOpsControl(control, params);
    setControlResult(result);
    setBusy(false);
    if (result.ok) {
      await reload();
    }
  }

  if (loading) {
    return (
      <div className="page-stack nx-founder-operator">
        <p className="muted">載入 Founder Live Operations…</p>
      </div>
    );
  }

  if (error || !snap) {
    return (
      <div className="page-stack nx-founder-operator" role="alert">
        <h1>Live Ops Access Denied</h1>
        <p className="muted">會員工作階段無法讀取 Founder Live Operations（403 fail-closed）。</p>
        <div className="tag tag-warn">{error || "denied"}</div>
      </div>
    );
  }

  return (
    <div className="page-stack nx-founder-operator">
      <header>
        <h1>Founder Live Operations</h1>
        <p className="muted">
          PUB18-C · {snap.actor.tier} · {snap.actor.identitySource} · {snap.generatedAt}
        </p>
        <div className="nx-founder-banner-row">
          <span className="tag tag-warn">founder-only</span>
          <span className="tag">banned_control_count={snap.banned_control_count ?? 0}</span>
          <span className="tag">exchangeWrite={String(snap.exchangeWriteEnabled)}</span>
          <span className="tag">mainnetShortcut={String(snap.mainnetShortcut)}</span>
        </div>
      </header>

      <section className="nx-card" aria-label="Allowed live ops controls">
        <h2 className="sm">Allowed controls</h2>
        <p className="muted sm">
          pause/resume ingest · disable provider/source · force read-only degraded · export evidence.
          Banned: trade now · override Risk · force LONG/SHORT · change leverage · enable mainnet.
        </p>
        <div className="nx-founder-banner-row" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
          <button type="button" disabled={busy} onClick={() => void runControl("pause_ingest")}>
            Pause ingest
          </button>
          <button type="button" disabled={busy} onClick={() => void runControl("resume_ingest")}>
            Resume ingest
          </button>
          <label className="muted sm">
            provider{" "}
            <input value={providerId} onChange={(e) => setProviderId(e.target.value)} />
          </label>
          <button
            type="button"
            disabled={busy}
            onClick={() => void runControl("disable_provider", { provider_id: providerId })}
          >
            Disable provider
          </button>
          <label className="muted sm">
            source{" "}
            <input value={sourceId} onChange={(e) => setSourceId(e.target.value)} />
          </label>
          <button
            type="button"
            disabled={busy}
            onClick={() => void runControl("disable_source", { source_id: sourceId })}
          >
            Disable source
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void runControl("force_read_only_degraded_mode")}
          >
            Force read-only degraded
          </button>
          <button type="button" disabled={busy} onClick={() => void runControl("export_evidence")}>
            Export evidence
          </button>
        </div>
        {controlResult ? (
          <pre className="mono sm nx-founder-json">{JSON.stringify(controlResult, null, 2)}</pre>
        ) : null}
      </section>

      <nav className="nx-founder-panel-jump" aria-label="Live ops panels">
        {FOUNDER_LIVE_OPS_NAV.map((item) => (
          <a key={item.id} href={`/founder/live-ops${item.hash}`}>
            {item.label}
          </a>
        ))}
      </nav>

      <div className="nx-founder-panels">
        {snap.panels.map((panel) => (
          <PanelCard key={panel.id} panel={panel} />
        ))}
      </div>
    </div>
  );
}
