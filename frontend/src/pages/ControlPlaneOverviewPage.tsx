import { useEffect, useState } from "react";

type FieldEnvelope = {
  value: unknown;
  source_service?: string;
  source_role?: string;
  source_timestamp?: number | null;
  received_at?: number;
  freshness_seconds?: number | null;
  freshness_sec?: number | null;
  data_status?: string;
  evidence_ref?: string;
  schema_version?: string;
};

type OverviewPayload = {
  system_mode?: Record<string, unknown>;
  service_health?: Record<string, FieldEnvelope>;
  demo_session?: Record<string, FieldEnvelope | string>;
  demo_account?: Record<string, FieldEnvelope | string>;
  market_funnel?: Record<string, FieldEnvelope>;
  market?: Record<string, FieldEnvelope>;
  current_execution?: Record<string, FieldEnvelope | string>;
  execution?: Record<string, FieldEnvelope | string>;
  performance?: Record<string, FieldEnvelope | string>;
  learning?: Record<string, FieldEnvelope | string | Record<string, unknown>>;
  why_no_trade?: {
    active?: boolean;
    headline?: string | null;
    detail?: string | null;
    gate_breakdown?: Record<string, unknown> | null;
  };
  version_labels?: Record<string, FieldEnvelope | string>;
  ownership?: Record<string, unknown>;
  safety?: Record<string, unknown>;
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
      ? status === "MISSING" || status === "SERVICE_UNAVAILABLE" || status === "UNAVAILABLE"
        ? status
        : "—"
      : String(field.value);
  return (
    <div className="nx-field">
      <span className="muted">{label}</span>
      <strong aria-label={`${label}: ${display} (${status})`}>{display}</strong>
      <small className="muted">
        {status} · {field.source_role || field.source_service || "?"}
        {field.evidence_ref ? ` · ${field.evidence_ref}` : ""}
      </small>
    </div>
  );
}

function val(field?: FieldEnvelope | string | null): string {
  if (!field) return "—";
  if (typeof field === "string") return field;
  if (field.value === null || field.value === undefined) return field.data_status || "MISSING";
  return String(field.value);
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
  const funnel = overview?.market_funnel || overview?.market;
  const exec = overview?.execution || overview?.current_execution;
  const why = overview?.why_no_trade;
  const learning = overview?.learning || {};
  const chain = (learning as { evidence_chain?: Record<string, FieldEnvelope> }).evidence_chain;

  return (
    <div className="nx-page" data-testid="control-plane-overview">
      <header>
        <h1>NEXUS</h1>
        <p className="muted">總覽 · 單一控制台 · 僅讀取 · MAINNET OFF · REAL MONEY OFF</p>
      </header>

      <nav aria-label="主要導覽" className="nx-mobile-nav">
        <a href="/control-plane">總覽</a>
        <a href="/universe">市場</a>
        <a href="/control-plane#execution">交易</a>
        <a href="/control-plane#learning">學習</a>
        <a href="/control-plane#health">更多</a>
      </nav>

      {loading && <p role="status">Loading…</p>}
      {error && (
        <p role="alert">Control Plane fetch error: {error}</p>
      )}

      <section aria-labelledby="mode-heading">
        <h2 id="mode-heading">模式</h2>
        <p>
          BYBIT DEMO · MAINNET {mode.mainnet ? "ON" : "OFF"} · REAL MONEY{" "}
          {mode.real_money ? "ON" : "OFF"} · FIXED {String(mode.fixed_leverage ?? 25)}X ·{" "}
          {String(mode.margin_mode ?? "ISOLATED")}
        </p>
        <p>
          EXECUTION OWNER: {String(mode.execution_owner || "DEMO_VALIDATION_SERVICE")} · Stage3
          Execution Disabled
        </p>
      </section>

      <section id="health" aria-labelledby="health-heading">
        <h2 id="health-heading">服務健康</h2>
        <Field label="Market Intelligence" field={overview?.service_health?.market_intelligence} />
        <Field label="Demo Execution" field={overview?.service_health?.demo_execution} />
        <Field label="Learning" field={overview?.service_health?.learning_engine} />
        <Field label="Control Plane" field={overview?.service_health?.control_plane} />
      </section>

      <section aria-labelledby="session-heading">
        <h2 id="session-heading">Demo Session</h2>
        <Field label="Session ID" field={overview?.demo_session?.session_id as FieldEnvelope} />
        <Field label="Status" field={overview?.demo_session?.status as FieldEnvelope} />
        <Field label="Started" field={overview?.demo_session?.started_at as FieldEnvelope} />
        <Field label="Ends" field={overview?.demo_session?.ends_at as FieldEnvelope} />
        <Field label="Remaining" field={overview?.demo_session?.remaining_seconds as FieldEnvelope} />
        <Field label="Entries" field={overview?.demo_session?.entries_total as FieldEnvelope} />
        <Field label="Entry Limit" field={overview?.demo_session?.entry_limit as FieldEnvelope} />
        <Field label="Trades" field={overview?.demo_session?.trades_completed as FieldEnvelope} />
        <Field label="Write Window" field={overview?.demo_session?.session_write_enabled as FieldEnvelope} />
        <Field
          label="Automatic Extension"
          field={overview?.demo_session?.automatic_extension as FieldEnvelope}
        />
      </section>

      <section aria-labelledby="account-heading">
        <h2 id="account-heading">帳戶</h2>
        {typeof overview?.demo_account?.note === "string" && (
          <p role="status">{overview.demo_account.note}</p>
        )}
        <Field label="Wallet" field={overview?.demo_account?.wallet_balance as FieldEnvelope} />
        <Field label="Equity" field={overview?.demo_account?.equity as FieldEnvelope} />
        <Field label="Available" field={overview?.demo_account?.available_balance as FieldEnvelope} />
        <Field label="Used Margin" field={overview?.demo_account?.used_margin as FieldEnvelope} />
        <Field label="Unrealized PnL" field={overview?.demo_account?.unrealized_pnl as FieldEnvelope} />
      </section>

      {why?.active && (
        <section aria-labelledby="why-heading" data-testid="why-no-trade">
          <h2 id="why-heading">為什麼沒有交易</h2>
          <p role="status">
            <strong>{why.headline || "NO_TRADE"}</strong>
          </p>
          <p>{why.detail}</p>
          {why.gate_breakdown && (
            <ul>
              {Object.entries(why.gate_breakdown).map(([k, v]) => (
                <li key={k}>
                  {k}: {v === null || v === undefined ? "MISSING" : String(v)}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <section aria-labelledby="funnel-heading">
        <h2 id="funnel-heading">漏斗</h2>
        <Field label="Candidates" field={funnel?.candidates_total} />
        <Field label="Risk Critic Blocks" field={funnel?.risk_critic_blocks} />
        <Field label="Mistake Guard Blocks" field={funnel?.mistake_guard_blocks} />
        <Field label="Cost Gate Blocks" field={funnel?.cost_gate_blocks} />
      </section>

      <section id="execution" aria-labelledby="exec-heading">
        <h2 id="exec-heading">執行</h2>
        <Field label="Current Candidate" field={exec?.current_candidate as FieldEnvelope} />
        <Field label="Position" field={exec?.open_position as FieldEnvelope} />
        <Field label="Orders" field={exec?.open_orders as FieldEnvelope} />
        <Field label="SL" field={exec?.stop_loss as FieldEnvelope} />
        <Field label="TP" field={exec?.take_profit as FieldEnvelope} />
        <Field label="Protection" field={exec?.protection_status as FieldEnvelope} />
        <Field label="Reconciliation" field={exec?.reconciliation as FieldEnvelope} />
      </section>

      <section aria-labelledby="perf-heading">
        <h2 id="perf-heading">績效</h2>
        <Field label="Gross PnL" field={overview?.performance?.gross_pnl as FieldEnvelope} />
        <Field label="Fees" field={overview?.performance?.total_fees as FieldEnvelope} />
        <Field label="Funding" field={overview?.performance?.funding as FieldEnvelope} />
        <Field label="Net PnL" field={overview?.performance?.net_pnl as FieldEnvelope} />
        <Field label="Drawdown" field={overview?.performance?.max_drawdown as FieldEnvelope} />
      </section>

      <section id="learning" aria-labelledby="learn-heading">
        <h2 id="learn-heading">學習／反思證據鏈</h2>
        <p className="muted">Trade → Outcome → Process → Reflection → Similar Case → Guard → Decision Delta</p>
        <Field label="Trade Case" field={chain?.source_trade_case_id} />
        <Field label="Outcome" field={chain?.outcome} />
        <Field label="Process Quality" field={chain?.process_quality} />
        <Field label="Reflection" field={chain?.reflection_summary} />
        <Field label="Similar Candidate" field={chain?.similar_candidate_id} />
        <Field label="Similarity" field={chain?.similarity_score} />
        <Field label="Before Verdict" field={chain?.before_verdict} />
        <Field label="After Verdict" field={chain?.after_verdict} />
        <Field label="Guard Action" field={chain?.guard_action} />
        <Field label="Policy" field={chain?.policy_version} />
        <Field
          label="Learning Effectiveness"
          field={(learning as { learning_effectiveness?: FieldEnvelope }).learning_effectiveness}
        />
        <p className="muted">學習結論不得升級為已證實、自我進化確認或可獲利。</p>
      </section>

      <section aria-labelledby="versions-heading">
        <h2 id="versions-heading">版本標籤（必須分開）</h2>
        <Field label="PR #6 Branch Head" field={overview?.version_labels?.pr6_branch_head as FieldEnvelope} />
        <Field
          label="Observation Deployed SHA"
          field={overview?.version_labels?.observation_deployed_code_sha as FieldEnvelope}
        />
        <Field label="Control Plane SHA" field={overview?.version_labels?.control_plane_sha as FieldEnvelope} />
        <Field label="Deploy Run" field={overview?.version_labels?.deploy_run as FieldEnvelope} />
        <p className="muted">
          PR head={val(overview?.version_labels?.pr6_branch_head as FieldEnvelope)} ≠ Observation SHA=
          {val(overview?.version_labels?.observation_deployed_code_sha as FieldEnvelope)}
        </p>
      </section>

      <section aria-labelledby="owner-heading">
        <h2 id="owner-heading">資料所有權</h2>
        <ul>
          <li>市場掃描 → market_intelligence</li>
          <li>Demo 帳戶／Session／持倉 → demo_execution</li>
          <li>反思／學習 → demo_execution</li>
        </ul>
        <p className="muted">
          服務名稱僅供系統健康／Operator Diagnostics；一般操作不要求分辨 Stage3／Validation。
        </p>
      </section>
    </div>
  );
}
