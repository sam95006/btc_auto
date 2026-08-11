import { useCallback, useEffect, useState } from "react";
import {
  fetchFounderDemoMonitor,
  fetchFounderLiveOps,
  postFounderLiveOpsControl,
} from "./api";
import type {
  FounderDemoMonitorSnapshot,
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

function fmt(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "number" && Number.isFinite(v)) {
    return Number.isInteger(v) ? String(v) : v.toFixed(6).replace(/\.?0+$/, "");
  }
  return String(v);
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

function laneTagClass(label: string | null | undefined): string {
  if (!label) return "tag-warn";
  if (label.includes("CANARY")) return "tag-warn";
  if (label.includes("RESEARCH")) return "tag-ok";
  return "tag-warn";
}

function ProvenanceFootnote({
  fieldKey,
  provenance,
}: {
  fieldKey: string;
  provenance?: Record<string, { source_timestamp?: string | null; freshness_sec?: number | null; lane?: string | null; provenance?: string }>;
}) {
  const meta = provenance?.[fieldKey];
  if (!meta) return null;
  return (
    <span className="muted sm mono">
      {" "}
      · {meta.provenance || "—"} · {meta.lane || "—"} · {meta.source_timestamp || "—"}
      {meta.freshness_sec != null ? ` · ${Math.round(meta.freshness_sec)}s` : ""}
    </span>
  );
}

function DemoMonitorPanel({
  monitor,
  error,
}: {
  monitor: FounderDemoMonitorSnapshot | null;
  error: string | null;
}) {
  if (error) {
    return (
      <section className="nx-card nx-founder-panel" id="demo-monitor" aria-label="Founder demo monitor">
        <div className="nx-founder-panel-head">
          <h2>Real Demo Monitor</h2>
          <span className="tag tag-bad">DENIED</span>
        </div>
        <p className="muted sm">Founder-only feed unreachable ({error}).</p>
      </section>
    );
  }

  if (!monitor) {
    return (
      <section className="nx-card nx-founder-panel" id="demo-monitor" aria-label="Founder demo monitor">
        <div className="nx-founder-panel-head">
          <h2>Real Demo Monitor</h2>
          <span className="tag tag-warn">LOADING</span>
        </div>
      </section>
    );
  }

  const pos = monitor.active_position;
  const wallet = monitor.wallet;
  const acct = monitor.accounting;
  const intel = monitor.trading_intel;
  const perf = monitor.performance;
  const learn = monitor.learning;
  const prov = monitor.field_provenance;
  const empty = !monitor.feed_ready;

  return (
    <section className="nx-card nx-founder-panel" id="demo-monitor" aria-label="Founder demo monitor">
      <div className="nx-founder-panel-head">
        <h2>Real Demo Monitor</h2>
        <span className={`tag tag-${empty ? "warn" : "ok"}`}>
          {empty ? monitor.feed_status : "FEED_READY"}
        </span>
      </div>
      <p className="muted sm">
        Founder-only · members inaccessible ·{" "}
        {empty
          ? "Agent B core/monitor feed not ready — fail-closed empty (no fabricated values)."
          : monitor.note}
      </p>
      <div className="nx-founder-banner-row">
        <span className="tag">demo UID {fmt(monitor.demo_uid_masked)}</span>
        <span className={`tag ${laneTagClass(monitor.lane_label)}`}>
          {monitor.lane_label || "LANE_UNLABELED"}
        </span>
        <span className="tag">
          equity {fmt(wallet.equity)} / Δ {fmt(wallet.delta)}
        </span>
        {monitor.position_state ? (
          <span className={`tag tag-${monitor.position_state === "FLAT" ? "warn" : "ok"}`}>
            {monitor.position_state}
          </span>
        ) : null}
        {monitor.source_timestamp ? (
          <span className="tag mono sm">as-of {monitor.source_timestamp}</span>
        ) : null}
        {monitor.fixture_removed ? <span className="tag tag-ok">live feed</span> : null}
        {monitor.fixture_used ? <span className="tag tag-warn">fixture fallback</span> : null}
      </div>

      {monitor.thesis ? (
        <>
          <h3 className="sm">Thesis / horizon</h3>
          <dl className="nx-founder-metrics">
            {Object.entries(monitor.thesis).map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd className="mono">{fmt(v)}</dd>
              </div>
            ))}
          </dl>
        </>
      ) : null}

      <h3 className="sm">Active position</h3>
      {pos.open ? (
        <dl className="nx-founder-metrics">
          <div>
            <dt>symbol</dt>
            <dd className="mono">{fmt(pos.symbol)}</dd>
          </div>
          <div>
            <dt>side</dt>
            <dd className="mono">{fmt(pos.side)}</dd>
          </div>
          <div>
            <dt>notional</dt>
            <dd className="mono">{fmt(pos.notional)}</dd>
          </div>
          <div>
            <dt>entry</dt>
            <dd className="mono">{fmt(pos.entry)}</dd>
          </div>
          <div>
            <dt>current</dt>
            <dd className="mono">{fmt(pos.current)}</dd>
          </div>
          <div>
            <dt>stop</dt>
            <dd className="mono">{fmt(pos.stop)}</dd>
          </div>
          <div>
            <dt>target</dt>
            <dd className="mono">{fmt(pos.target)}</dd>
          </div>
          <div>
            <dt>initial target</dt>
            <dd className="mono">{fmt(pos.initial_target)}</dd>
          </div>
          <div>
            <dt>dynamic profit zone</dt>
            <dd className="mono">
              {pos.dynamic_profit_zone ? JSON.stringify(pos.dynamic_profit_zone) : "—"}
            </dd>
          </div>
          <div>
            <dt>unrealized PnL</dt>
            <dd className="mono">{fmt(pos.unrealized_pnl)}</dd>
          </div>
          <div>
            <dt>expected net target</dt>
            <dd className="mono">{fmt(pos.expected_net_target)}</dd>
          </div>
          <div>
            <dt>expected time to target</dt>
            <dd className="mono">{fmt(pos.expected_time_to_target)}</dd>
          </div>
          <div>
            <dt>strategy horizon</dt>
            <dd className="mono">{fmt(pos.strategy_horizon)}</dd>
          </div>
          <div>
            <dt>hold duration</dt>
            <dd className="mono">{fmt(pos.hold_duration)}</dd>
          </div>
          <div>
            <dt>est. net if closed</dt>
            <dd className="mono">{fmt(pos.estimated_net_if_closed)}</dd>
          </div>
        </dl>
      ) : (
        <p className="muted sm">
          FLAT — no open position
          {empty ? " (feed empty)" : " (live exchange verified)."}
        </p>
      )}

      <h3 className="sm">MFE / MAE</h3>
      <dl className="nx-founder-metrics">
        <div>
          <dt>MFE</dt>
          <dd className="mono">
            {fmt(intel?.mfe ?? monitor.mfe ?? pos.mfe)}
            <ProvenanceFootnote fieldKey="mfe" provenance={prov} />
          </dd>
        </div>
        <div>
          <dt>MAE</dt>
          <dd className="mono">
            {fmt(intel?.mae ?? monitor.mae ?? pos.mae)}
            <ProvenanceFootnote fieldKey="mae" provenance={prov} />
          </dd>
        </div>
        <div>
          <dt>MFE capture estimate</dt>
          <dd className="mono">
            {fmt(intel?.mfe_capture_estimate)}
            <ProvenanceFootnote fieldKey="trading_intel.mfe_capture_estimate" provenance={prov} />
          </dd>
        </div>
      </dl>

      <h3 className="sm">Trading intelligence</h3>
      <dl className="nx-founder-metrics">
        <div>
          <dt>side / state</dt>
          <dd className="mono">
            {fmt(intel?.side)} / {fmt(intel?.position_state ?? monitor.position_state)}
            <ProvenanceFootnote fieldKey="trading_intel.side" provenance={prov} />
          </dd>
        </div>
        <div>
          <dt>entry / current / SL</dt>
          <dd className="mono">
            {fmt(intel?.entry)} / {fmt(intel?.current)} / {fmt(intel?.stop_loss)}
            <ProvenanceFootnote fieldKey="trading_intel.entry" provenance={prov} />
          </dd>
        </div>
        <div>
          <dt>initial target / profit zone</dt>
          <dd className="mono">
            {fmt(intel?.initial_target)} /{" "}
            {intel?.dynamic_profit_zone ? JSON.stringify(intel.dynamic_profit_zone) : "—"}
            <ProvenanceFootnote fieldKey="trading_intel.initial_target" provenance={prov} />
          </dd>
        </div>
        <div>
          <dt>unrealized / est. net if closed</dt>
          <dd className="mono">
            {fmt(intel?.unrealized_pnl)} / {fmt(intel?.estimated_net_if_closed)}
            <ProvenanceFootnote fieldKey="trading_intel.estimated_net_if_closed" provenance={prov} />
          </dd>
        </div>
        <div>
          <dt>remaining net edge</dt>
          <dd className="mono">
            {fmt(intel?.remaining_net_edge)}
            <ProvenanceFootnote fieldKey="trading_intel.remaining_net_edge" provenance={prov} />
          </dd>
        </div>
        <div>
          <dt>continuation score</dt>
          <dd className="mono">
            {fmt(intel?.continuation_score)}
            <ProvenanceFootnote fieldKey="trading_intel.continuation_score" provenance={prov} />
          </dd>
        </div>
        <div>
          <dt>giveback risk</dt>
          <dd className="mono">
            {fmt(intel?.giveback_risk)}
            <ProvenanceFootnote fieldKey="trading_intel.giveback_risk" provenance={prov} />
          </dd>
        </div>
        <div>
          <dt>AI thesis</dt>
          <dd className="mono">
            {intel?.ai_thesis && typeof intel.ai_thesis === "object"
              ? JSON.stringify(intel.ai_thesis)
              : fmt(intel?.ai_thesis)}
            <ProvenanceFootnote fieldKey="trading_intel.ai_thesis" provenance={prov} />
          </dd>
        </div>
        <div>
          <dt>last AI position review</dt>
          <dd className="mono">
            {intel?.last_ai_position_review && typeof intel.last_ai_position_review === "object"
              ? JSON.stringify(intel.last_ai_position_review)
              : fmt(intel?.last_ai_position_review)}
            <ProvenanceFootnote fieldKey="trading_intel.last_ai_position_review" provenance={prov} />
          </dd>
        </div>
        <div>
          <dt>last exit reason</dt>
          <dd className="mono">
            {fmt(intel?.last_exit_reason ?? acct.last_exit_reason)}
            <ProvenanceFootnote fieldKey="trading_intel.last_exit_reason" provenance={prov} />
          </dd>
        </div>
      </dl>

      <h3 className="sm">Performance</h3>
      <dl className="nx-founder-metrics">
        <div>
          <dt>win rate (long / short / agg)</dt>
          <dd className="mono">
            {fmt(perf?.win_rate_long)} / {fmt(perf?.win_rate_short)} / {fmt(perf?.win_rate_aggregate)}
            <ProvenanceFootnote fieldKey="performance.win_rate_aggregate" provenance={prov} />
          </dd>
        </div>
        <div>
          <dt>net PnL</dt>
          <dd className="mono">
            {fmt(perf?.net_pnl)}
            <ProvenanceFootnote fieldKey="performance.net_pnl" provenance={prov} />
          </dd>
        </div>
        <div>
          <dt>profit factor</dt>
          <dd className="mono">
            {fmt(perf?.profit_factor)}
            <ProvenanceFootnote fieldKey="performance.profit_factor" provenance={prov} />
          </dd>
        </div>
      </dl>

      <h3 className="sm">Learning</h3>
      {learn?.mistake_signatures?.length || learn?.pending_candidate_lessons?.length ? (
        <dl className="nx-founder-metrics">
          <div>
            <dt>mistake signatures</dt>
            <dd className="mono">
              <MetricValue value={learn.mistake_signatures} />
              <ProvenanceFootnote fieldKey="learning.mistake_signatures" provenance={prov} />
            </dd>
          </div>
          <div>
            <dt>pending candidate lessons</dt>
            <dd className="mono">
              <MetricValue value={learn.pending_candidate_lessons} />
              <ProvenanceFootnote
                fieldKey="learning.pending_candidate_lessons"
                provenance={prov}
              />
            </dd>
          </div>
        </dl>
      ) : (
        <p className="muted sm">No mistake signatures or pending candidate lessons in live feed.</p>
      )}

      <h3 className="sm">Accounting</h3>
      <dl className="nx-founder-metrics">
        <div>
          <dt>last exit reason</dt>
          <dd className="mono">{fmt(acct.last_exit_reason)}</dd>
        </div>
        <div>
          <dt>exchange closed PnL</dt>
          <dd className="mono">{fmt(acct.exchange_closed_pnl)}</dd>
        </div>
        <div>
          <dt>fees</dt>
          <dd className="mono">{fmt(acct.fees)}</dd>
        </div>
        <div>
          <dt>calculated net</dt>
          <dd className="mono">{fmt(acct.calculated_net)}</dd>
        </div>
        <div>
          <dt>wallet delta</dt>
          <dd className="mono">{fmt(acct.wallet_delta)}</dd>
        </div>
        <div>
          <dt>wallet reconciliation</dt>
          <dd className="mono">{fmt(acct.wallet_reconciliation_status)}</dd>
        </div>
      </dl>
      <div className="tag">founder-only · memberAccessible=false · no member execution</div>
    </section>
  );
}

/**
 * PUB18-C Founder Live Operations + V18.2.25 founder-only demo monitor.
 * Allowed controls only: pause/resume ingest, disable provider/source,
 * force read-only degraded, export evidence.
 */
export function FounderLiveOpsPage() {
  const [snap, setSnap] = useState<FounderLiveOpsSnapshot | null>(null);
  const [monitor, setMonitor] = useState<FounderDemoMonitorSnapshot | null>(null);
  const [monitorError, setMonitorError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [controlResult, setControlResult] = useState<FounderLiveOpsControlResult | null>(null);
  const [providerId, setProviderId] = useState("primary_chat");
  const [sourceId, setSourceId] = useState("bybit_public_v5");

  const reloadMonitor = useCallback(async () => {
    const result = await fetchFounderDemoMonitor();
    if (!result.ok) {
      setMonitorError(("error" in result && result.error) || "demo_monitor_denied");
      setMonitor(null);
      return;
    }
    setMonitorError(null);
    setMonitor(result as FounderDemoMonitorSnapshot);
  }, []);

  const reload = useCallback(async () => {
    const result = await fetchFounderLiveOps();
    if (!result.ok) {
      setError(("error" in result && result.error) || "live_ops_denied");
      setSnap(null);
      return;
    }
    setError(null);
    setSnap(result as FounderLiveOpsSnapshot);
    await reloadMonitor();
  }, [reloadMonitor]);

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
      const mon = await fetchFounderDemoMonitor();
      if (cancelled) return;
      if (!mon.ok) {
        setMonitorError(("error" in mon && mon.error) || "demo_monitor_denied");
        setMonitor(null);
      } else {
        setMonitor(mon as FounderDemoMonitorSnapshot);
      }
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

      <DemoMonitorPanel monitor={monitor} error={monitorError} />

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
        <a href="/founder/live-ops#demo-monitor">Demo Monitor</a>
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
