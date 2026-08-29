/**
 * PERSONAL-1 — Personal Market Intelligence product surface.
 *
 * The backend is the sole authority for Authentication AND Entitlement AND
 * Quota. This page only *reflects* the backend's decision: it renders locked /
 * upgrade / usage / unavailable states, and it never fabricates entitlement,
 * market data, signals, or a risk score on the client. Metered actions send a
 * stable idempotency key so a retry never double-charges quota.
 *
 * This is a member-safe surface: no trading execution, order routing, ARM,
 * position sizing, or Founder controls are present or reachable here.
 */
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import {
  addPersonalWatchlist,
  getBillingUsage,
  getPersonalFeatures,
  getPersonalHistory,
  getPersonalRisk,
  getPersonalSignals,
  getPersonalWatchlist,
  newIdempotencyKey,
  removePersonalWatchlist,
  runPersonalAnalysis,
  runPersonalReport,
  type BillingUsage,
  type PersonalAnalysis,
  type PersonalFeature,
  type PersonalFeatures,
  type PersonalReport,
} from "../services/stagingApi";

function RequireSession({ children }: { children: ReactNode }) {
  const { session, ready } = useAuth();
  if (!ready) return null;
  return session ? <>{children}</> : <Navigate to="/login" replace />;
}

export function IntelligencePage() {
  return (
    <RequireSession>
      <IntelligenceInner />
    </RequireSession>
  );
}

function IntelligenceInner() {
  const [features, setFeatures] = useState<PersonalFeatures | null>(null);
  const [usage, setUsage] = useState<BillingUsage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setFeatures(await getPersonalFeatures());
    } catch {
      setError("目前無法載入產品權限，請稍後再試。");
    } finally {
      setLoading(false);
    }
    try {
      setUsage(await getBillingUsage());
    } catch {
      setUsage(null);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const refreshUsage = useCallback(async () => {
    try {
      setUsage(await getBillingUsage());
    } catch {
      /* keep last-known usage; a metering outage must not break actions */
    }
  }, []);

  if (loading) {
    return (
      <IntelShell>
        <div className="mpv1-card" aria-busy="true">
          <p className="mpv1-muted">載入智慧分析中…</p>
        </div>
      </IntelShell>
    );
  }
  if (error || !features) {
    return (
      <IntelShell>
        <div className="mpv1-card" role="alert">
          <p>{error || "無法載入。"}</p>
          <button type="button" className="mpv1-btn mpv1-btn-outline" onClick={() => void load()}>
            重新載入
          </button>
        </div>
      </IntelShell>
    );
  }

  const feature = (key: string): PersonalFeature | undefined =>
    features.features.find((f) => f.key === key);
  const entitled = (key: string): boolean => Boolean(feature(key)?.entitled);

  return (
    <IntelShell plan={features.effective_plan_code}>
      <FeatureMatrix features={features.features} />
      <MeteredAction
        title="進階分析"
        featureKey="advanced_analysis"
        entitled={entitled("advanced_analysis")}
        onRefreshUsage={refreshUsage}
        usage={usage}
        run={runPersonalAnalysis}
        render={(r) => <AnalysisResult analysis={r.analysis} remaining={r.remaining} />}
      />
      <MeteredAction
        title="報告產生"
        featureKey="report_generation"
        entitled={entitled("report_generation")}
        onRefreshUsage={refreshUsage}
        usage={usage}
        run={runPersonalReport}
        render={(r) => <ReportResult report={r.report} remaining={r.remaining} />}
      />
      <WatchlistPanel entitled={entitled("watchlists")} />
      <HistoryPanel entitled={entitled("extended_market_history")} />
      <UnavailablePanel
        title="進階訊號"
        entitled={entitled("advanced_signals")}
        load={async () => {
          const r = await getPersonalSignals();
          return r.available;
        }}
      />
      <UnavailablePanel
        title="風險情報"
        entitled={entitled("risk_intelligence")}
        load={async () => {
          const r = await getPersonalRisk();
          return r.available;
        }}
      />
    </IntelShell>
  );
}

function IntelShell({ children, plan }: { children: ReactNode; plan?: string }) {
  return (
    <>
      <div className="mpv1-page-head">
        <div>
          <h1 className="mpv1-page-title">智慧分析</h1>
          <p className="mpv1-page-sub">
            所有付費功能的權限與額度皆以後端為準{plan ? `（目前方案：${plan.toUpperCase()}）` : ""}。
          </p>
        </div>
      </div>
      <div style={{ display: "grid", gap: "1rem" }}>{children}</div>
    </>
  );
}

// --------------------------------------------------------------------------
// Access matrix
// --------------------------------------------------------------------------

function FeatureMatrix({ features }: { features: PersonalFeature[] }) {
  return (
    <section className="mpv1-card" data-testid="feature-matrix">
      <h2 className="mpv1-card-title">產品權限總覽</h2>
      <div style={{ display: "grid", gap: "0.5rem" }}>
        {features.map((f) => (
          <div
            key={f.key}
            data-testid={`feature-${f.key}`}
            style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem", alignItems: "center" }}
          >
            <span>{f.label}</span>
            {!f.available ? (
              <span className="mpv1-chip" data-testid={`state-${f.key}`}>
                即將推出
              </span>
            ) : f.entitled ? (
              <span className="mpv1-chip" data-testid={`state-${f.key}`} style={{ color: "#2d7" }}>
                已解鎖
              </span>
            ) : (
              <Link
                className="mpv1-btn mpv1-btn-outline mpv1-btn-sm"
                to="/app/membership"
                data-testid={`upgrade-${f.key}`}
              >
                升級解鎖
              </Link>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

// --------------------------------------------------------------------------
// Metered actions (analysis / report)
// --------------------------------------------------------------------------

type MeteredResult<T> = { ok: boolean; status: number; body: (T & { remaining: number }) | null };

function MeteredAction<T>({
  title,
  featureKey,
  entitled,
  usage,
  onRefreshUsage,
  run,
  render,
}: {
  title: string;
  featureKey: string;
  entitled: boolean;
  usage: BillingUsage | null;
  onRefreshUsage: () => Promise<void>;
  run: (symbol: string, idem: string) => Promise<MeteredResult<T>>;
  render: (body: T & { remaining: number }) => ReactNode;
}) {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<(T & { remaining: number }) | null>(null);
  const [notice, setNotice] = useState("");

  const quotaCode =
    featureKey === "advanced_analysis" ? "advanced_analysis_requests_daily" : "report_generation_monthly";
  const quota = usage?.quotas.find((q) => q.quota_code === quotaCode) || null;

  if (!entitled) {
    return <LockedCard title={title} testid={featureKey} />;
  }

  async function onRun() {
    setBusy(true);
    setNotice("");
    setResult(null);
    try {
      // A single idempotency key for this attempt: a retried network call for
      // the *same* click cannot double-charge quota.
      const res = await run(symbol.trim().toUpperCase(), newIdempotencyKey(featureKey));
      if (res.ok && res.body) {
        setResult(res.body);
      } else if (res.status === 429) {
        setNotice("本期額度已用完，升級方案可獲得更多額度。");
      } else if (res.status === 503) {
        setNotice("目前市場資料無法取得，請稍後再試（未扣除額度）。");
      } else if (res.status === 403) {
        setNotice("此功能需要更高方案。");
      } else if (res.status === 400) {
        setNotice("請輸入有效的標的。");
      } else {
        setNotice("目前無法完成，請稍後再試。");
      }
    } finally {
      setBusy(false);
      void onRefreshUsage();
    }
  }

  return (
    <section className="mpv1-card" data-testid={`action-${featureKey}`}>
      <h2 className="mpv1-card-title">{title}</h2>
      {quota ? (
        <p className="mpv1-muted" data-testid={`quota-${featureKey}`}>
          本期額度：{quota.used} / {quota.limit}（剩餘 {quota.remaining}）
        </p>
      ) : null}
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
        <div className="mpv1-input" style={{ maxWidth: "12rem" }}>
          <input value={symbol} onChange={(e) => setSymbol(e.target.value)} aria-label="標的" />
        </div>
        <button
          type="button"
          className="mpv1-btn mpv1-btn-primary"
          disabled={busy || quota?.remaining === 0}
          onClick={() => void onRun()}
          data-testid={`run-${featureKey}`}
        >
          {busy ? "處理中…" : "執行"}
        </button>
      </div>
      {notice ? (
        <p className="mpv1-muted" role="status" style={{ marginTop: "0.5rem" }}>
          {notice}
        </p>
      ) : null}
      {result ? <div style={{ marginTop: "0.75rem" }}>{render(result)}</div> : null}
    </section>
  );
}

function AnalysisResult({ analysis, remaining }: { analysis: PersonalAnalysis; remaining: number }) {
  return (
    <div data-testid="analysis-result" data-classification={analysis.data_class}>
      <p>
        {analysis.symbol}：趨勢 <strong>{analysis.trend}</strong>，波動度 <strong>{analysis.volatility}</strong>
      </p>
      <p className="mpv1-muted">
        變化 {analysis.change_pct}%、區間 {analysis.range_pct}%、樣本 {analysis.points} 筆 · 剩餘額度 {remaining}
      </p>
    </div>
  );
}

function ReportResult({ report, remaining }: { report: PersonalReport; remaining: number }) {
  return (
    <div data-testid="report-result" data-classification={report.data_class}>
      <p>{report.summary}</p>
      <ul className="mpv1-muted">
        {report.sections.map((s, i) => (
          <li key={i}>
            {s.title}：{String(s.value)}
          </li>
        ))}
      </ul>
      <p className="mpv1-muted">剩餘額度 {remaining}</p>
    </div>
  );
}

// --------------------------------------------------------------------------
// Watchlist (capacity)
// --------------------------------------------------------------------------

function WatchlistPanel({ entitled }: { entitled: boolean }) {
  const [symbols, setSymbols] = useState<string[]>([]);
  const [capacity, setCapacity] = useState(0);
  const [input, setInput] = useState("");
  const [notice, setNotice] = useState("");
  const [ready, setReady] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await getPersonalWatchlist();
      setSymbols(r.symbols);
      setCapacity(r.capacity);
    } catch {
      /* leave empty; entitlement gate covers 403 */
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    if (entitled) void load();
  }, [entitled, load]);

  if (!entitled) return <LockedCard title="觀察清單" testid="watchlists" />;

  async function onAdd() {
    setNotice("");
    const res = await addPersonalWatchlist(input.trim().toUpperCase());
    if (res.ok && res.body) {
      setSymbols(res.body.symbols);
      setCapacity(res.body.capacity);
      setInput("");
    } else if (res.status === 409) {
      setNotice("已達方案上限，升級可加入更多標的。");
    } else if (res.status === 400) {
      setNotice("請輸入有效的標的。");
    } else {
      setNotice("目前無法加入。");
    }
  }

  async function onRemove(sym: string) {
    const res = await removePersonalWatchlist(sym);
    if (res.ok && res.body) setSymbols(res.body.symbols);
  }

  return (
    <section className="mpv1-card" data-testid="action-watchlists">
      <h2 className="mpv1-card-title">觀察清單</h2>
      <p className="mpv1-muted" data-testid="watchlist-capacity">
        已使用 {symbols.length} / {capacity}
      </p>
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <div className="mpv1-input" style={{ maxWidth: "12rem" }}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            aria-label="加入標的"
            placeholder="例如 ETHUSDT"
          />
        </div>
        <button
          type="button"
          className="mpv1-btn mpv1-btn-primary"
          disabled={!input.trim() || symbols.length >= capacity}
          onClick={() => void onAdd()}
          data-testid="watchlist-add"
        >
          加入
        </button>
      </div>
      {notice ? (
        <p className="mpv1-muted" role="status" style={{ marginTop: "0.5rem" }}>
          {notice}
        </p>
      ) : null}
      {ready && symbols.length === 0 ? (
        <p className="mpv1-muted" style={{ marginTop: "0.5rem" }}>
          尚未加入任何標的。
        </p>
      ) : (
        <ul style={{ marginTop: "0.5rem", display: "grid", gap: "0.25rem" }}>
          {symbols.map((s) => (
            <li key={s} style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
              <span>{s}</span>
              <button
                type="button"
                className="mpv1-btn mpv1-btn-outline mpv1-btn-sm"
                onClick={() => void onRemove(s)}
                data-testid={`watchlist-remove-${s}`}
              >
                移除
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// --------------------------------------------------------------------------
// History (range clamp by plan)
// --------------------------------------------------------------------------

function HistoryPanel({ entitled }: { entitled: boolean }) {
  const [info, setInfo] = useState<{ effective_days: number; max_days: number; clamped: boolean } | null>(null);

  useEffect(() => {
    if (!entitled) return;
    // Request more than any plan grants; the backend clamps to plan policy.
    getPersonalHistory("BTCUSDT", 3650)
      .then((r) => setInfo({ effective_days: r.effective_days, max_days: r.max_days, clamped: r.clamped }))
      .catch(() => setInfo(null));
  }, [entitled]);

  if (!entitled) return <LockedCard title="延伸歷史" testid="extended_market_history" />;

  return (
    <section className="mpv1-card" data-testid="action-extended_market_history">
      <h2 className="mpv1-card-title">延伸歷史</h2>
      {info ? (
        <p className="mpv1-muted" data-testid="history-range">
          方案可查詢範圍：最多 {info.max_days} 天（本次生效 {info.effective_days} 天{info.clamped ? "，已依方案上限裁切" : ""}）。
        </p>
      ) : (
        <p className="mpv1-muted" aria-busy="true">
          載入中…
        </p>
      )}
    </section>
  );
}

// --------------------------------------------------------------------------
// Unavailable member-safe panels (signals / risk) — never fabricated
// --------------------------------------------------------------------------

function UnavailablePanel({
  title,
  entitled,
  load,
}: {
  title: string;
  entitled: boolean;
  load: () => Promise<boolean>;
}) {
  const [available, setAvailable] = useState<boolean | null>(null);

  useEffect(() => {
    if (!entitled) return;
    load()
      .then(setAvailable)
      .catch(() => setAvailable(false));
  }, [entitled]);

  if (!entitled) return <LockedCard title={title} testid={title} />;

  return (
    <section className="mpv1-card" data-testid={`action-${title}`}>
      <h2 className="mpv1-card-title">{title}</h2>
      {available === true ? (
        <p className="mpv1-muted">資料可用。</p>
      ) : (
        // Entitled but no real backend yet: show an explicit unavailable state.
        // We never fill this with fabricated signals or a fake risk score.
        <p className="mpv1-muted" role="status" data-testid="unavailable">
          此功能的即時資料尚未開放，開放後會在此顯示。目前不會提供任何模擬或推測資料。
        </p>
      )}
    </section>
  );
}

// --------------------------------------------------------------------------
// Shared locked card
// --------------------------------------------------------------------------

function LockedCard({ title, testid }: { title: string; testid: string }) {
  return (
    <section className="mpv1-card" data-testid={`locked-${testid}`}>
      <h2 className="mpv1-card-title">{title}</h2>
      <p className="mpv1-muted">此功能需要更高方案才能使用。</p>
      <Link className="mpv1-btn mpv1-btn-primary mpv1-btn-sm" to="/app/membership" data-testid={`locked-upgrade-${testid}`}>
        升級解鎖
      </Link>
    </section>
  );
}
