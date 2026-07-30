import { useEffect, useState } from "react";

type FieldEnvelope = {
  value: unknown;
  source_service?: string;
  source_timestamp?: number | null;
  freshness_sec?: number | null;
  data_status?: string;
  evidence_ref?: string;
};

type OverviewPayload = {
  system_mode?: Record<string, unknown>;
  service_health?: Record<string, FieldEnvelope>;
  demo_session?: Record<string, FieldEnvelope | string>;
  demo_account?: Record<string, FieldEnvelope | string>;
  market_funnel?: Record<string, FieldEnvelope>;
  current_execution?: Record<string, FieldEnvelope | string>;
  performance?: Record<string, FieldEnvelope | string>;
  learning?: Record<string, FieldEnvelope | string>;
  ownership?: Record<string, string>;
  error?: string;
  note?: string;
};

function Field({ label, field }: { label: string; field?: FieldEnvelope | string | null }) {
  if (!field || typeof field === "string") {
    return (
      <div className="nx-field">
        <span className="muted">{label}</span>
        <strong>{field ?? "—"}</strong>
      </div>
    );
  }
  const status = field.data_status || "UNKNOWN";
  const display =
    field.value === null || field.value === undefined
      ? status === "MISSING" || status === "SERVICE_UNAVAILABLE"
        ? status
        : "—"
      : String(field.value);
  return (
    <div className="nx-field">
      <span className="muted">{label}</span>
      <strong>{display}</strong>
      <small className="muted">
        {status} · {field.source_service || "?"}
        {field.evidence_ref ? ` · ${field.evidence_ref}` : ""}
      </small>
    </div>
  );
}

/**
 * Unified NEXUS Control Plane Overview — read-only federation view.
 * Does not hardcode service hosts; fetches backend control-plane API only.
 */
export function ControlPlaneOverviewPage() {
  const [overview, setOverview] = useState<OverviewPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/nexus/control-plane/overview");
        const data = await res.json();
        if (cancelled) return;
        setOverview((data?.overview as OverviewPayload) || null);
        setError(null);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "fetch_failed");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const mode = overview?.system_mode || {};

  return (
    <div className="nx-page" data-testid="control-plane-overview">
      <header>
        <h1>NEXUS Control Plane</h1>
        <p className="muted">
          單一 Overview · 後端服務隔離 · 僅讀取 · Execution Owner = Demo Validation
        </p>
      </header>

      {loading && <p>Loading…</p>}
      {error && <p role="alert">Control Plane fetch error: {error}</p>}

      <section>
        <h2>1. System Mode</h2>
        <p>
          BYBIT DEMO · MAINNET {mode.mainnet ? "ON" : "OFF"} · REAL MONEY{" "}
          {mode.real_money ? "ON" : "OFF"} · FIXED {String(mode.fixed_leverage ?? 25)}X ·{" "}
          {String(mode.margin_mode ?? "ISOLATED")}
        </p>
        <p className="muted">
          Stage3 Execution Disabled Permanently · Owner: {String(mode.execution_owner || "DEMO_VALIDATION_SERVICE")}
        </p>
      </section>

      <section>
        <h2>2. Service Health</h2>
        <Field label="Market Intelligence" field={overview?.service_health?.market_intelligence} />
        <Field label="Demo Execution" field={overview?.service_health?.demo_execution} />
        <Field label="Learning Engine" field={overview?.service_health?.learning_engine} />
        <Field label="Control Plane" field={overview?.service_health?.control_plane} />
      </section>

      <section>
        <h2>3. Demo Session</h2>
        <Field label="Session ID" field={overview?.demo_session?.session_id as FieldEnvelope} />
        <Field label="Status" field={overview?.demo_session?.status as FieldEnvelope} />
        <Field label="Started At" field={overview?.demo_session?.started_at as FieldEnvelope} />
        <Field label="Entries" field={overview?.demo_session?.entries_total as FieldEnvelope} />
        <Field label="Trades" field={overview?.demo_session?.trades_completed as FieldEnvelope} />
        <Field label="Write Enabled" field={overview?.demo_session?.session_write_enabled as FieldEnvelope} />
      </section>

      <section>
        <h2>4. Demo Account</h2>
        {typeof overview?.demo_account?.note === "string" && (
          <p role="status">{overview.demo_account.note}</p>
        )}
        <Field label="Wallet" field={overview?.demo_account?.wallet_balance as FieldEnvelope} />
        <Field label="Equity" field={overview?.demo_account?.equity as FieldEnvelope} />
        <Field label="Available" field={overview?.demo_account?.available_balance as FieldEnvelope} />
        <Field label="Used Margin" field={overview?.demo_account?.used_margin as FieldEnvelope} />
        <Field label="Unrealized PnL" field={overview?.demo_account?.unrealized_pnl as FieldEnvelope} />
      </section>

      <section>
        <h2>5. Market Funnel</h2>
        <Field label="Candidates" field={overview?.market_funnel?.candidates_total} />
        <Field label="Risk Critic Blocks" field={overview?.market_funnel?.risk_critic_blocks} />
        <Field label="Mistake Guard Blocks" field={overview?.market_funnel?.mistake_guard_blocks} />
        <Field label="Cost Gate Blocks" field={overview?.market_funnel?.cost_gate_blocks} />
      </section>

      <section>
        <h2>6–8. Execution / Performance / Learning</h2>
        <Field label="Open Position" field={overview?.current_execution?.open_position as FieldEnvelope} />
        <Field label="Gross PnL" field={overview?.performance?.gross_pnl as FieldEnvelope} />
        <Field label="Fees" field={overview?.performance?.total_fees as FieldEnvelope} />
        <Field label="Funding" field={overview?.performance?.funding as FieldEnvelope} />
        <Field label="Net PnL" field={overview?.performance?.net_pnl as FieldEnvelope} />
        <Field label="Decision Deltas" field={overview?.learning?.decision_delta_count as FieldEnvelope} />
      </section>

      <section>
        <h2>Ownership</h2>
        <ul>
          <li>Market Scan → {overview?.ownership?.market_scan || "market_intelligence"}</li>
          <li>Demo Wallet → {overview?.ownership?.demo_wallet || "demo_execution"}</li>
          <li>Demo Session → {overview?.ownership?.demo_session || "demo_execution"}</li>
          <li>Positions → {overview?.ownership?.positions_orders || "demo_execution"}</li>
          <li>Reflection → {overview?.ownership?.outcome_reflection || "demo_execution"}</li>
        </ul>
        <p className="muted">市場分析：Stage3／Market Intelligence · 實際 Demo 下單：Demo Validation</p>
      </section>
    </div>
  );
}
