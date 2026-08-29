import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { MarketingHeader, AuthFooter } from "../layout/Shells";
import {
  cancelBillingSubscription,
  getBillingEntitlements,
  getBillingPlans,
  getBillingSubscription,
  getBillingUsage,
  openBillingPortal,
  startBillingCheckout,
  type BillingEntitlements,
  type BillingPlan,
  type BillingSubscription,
  type BillingUsage,
} from "../services/stagingApi";
import { entitlementLabel, isSelfServicePlan, planTagline, statusLabel } from "../billing/presentation";

function RequireSession({ children }: { children: ReactNode }) {
  const { session, ready } = useAuth();
  if (!ready) return null;
  return session ? <>{children}</> : <Navigate to="/login" replace />;
}

const ACTIVE_STATUSES = new Set(["active", "trialing"]);

// ---------------------------------------------------------------------------
// Billing center (plans + current subscription + management)
// ---------------------------------------------------------------------------

export function BillingCenterPage() {
  return (
    <RequireSession>
      <BillingCenterInner />
    </RequireSession>
  );
}

function BillingCenterInner() {
  const [plans, setPlans] = useState<BillingPlan[]>([]);
  const [subscription, setSubscription] = useState<BillingSubscription | null>(null);
  const [entitlements, setEntitlements] = useState<BillingEntitlements | null>(null);
  const [usage, setUsage] = useState<BillingUsage | null>(null);
  const [usageError, setUsageError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyPlan, setBusyPlan] = useState<string | null>(null);
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [p, s, e] = await Promise.all([
        getBillingPlans(),
        getBillingSubscription(),
        getBillingEntitlements(),
      ]);
      setPlans(p.plans);
      setSubscription(s.subscription);
      setEntitlements(e);
    } catch {
      setError("目前無法載入帳務資訊，請稍後再試。");
    } finally {
      setLoading(false);
    }
    // Usage is loaded separately so a metering outage does not break the page.
    try {
      setUsage(await getBillingUsage());
      setUsageError(false);
    } catch {
      setUsage(null);
      setUsageError(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function onUpgrade(planCode: string) {
    setBusyPlan(planCode);
    setNotice("");
    try {
      const res = await startBillingCheckout(planCode);
      const url = res.body?.checkout?.checkout_url;
      if (res.ok && url) {
        // The server owns the hosted checkout URL; the browser only redirects.
        window.location.href = url;
        return;
      }
      if (res.status === 503) {
        setNotice("線上付款目前尚未開放，請稍後再試或聯絡我們。");
      } else if (res.status === 400) {
        setNotice("此方案無法自助購買。");
      } else {
        setNotice("無法開始結帳，請稍後再試。");
      }
    } finally {
      setBusyPlan(null);
    }
  }

  async function onCancel() {
    setNotice("");
    const res = await cancelBillingSubscription();
    if (res.ok) {
      setNotice("已送出取消要求，訂閱將於本期結束後結束。實際狀態以帳務系統確認為準。");
      void load();
    } else {
      setNotice("目前無法處理取消要求。");
    }
  }

  async function onPortal() {
    const res = await openBillingPortal();
    const url = res.body?.portal?.portal_url;
    if (res.ok && url) {
      window.location.href = url;
    } else {
      setNotice("帳務管理入口目前尚未開放。");
    }
  }

  if (loading) {
    return (
      <BillingShell>
        <div className="mpv1-card" aria-busy="true">
          <p className="mpv1-muted">載入帳務資訊中…</p>
        </div>
      </BillingShell>
    );
  }
  if (error) {
    return (
      <BillingShell>
        <div className="mpv1-card" role="alert">
          <p>{error}</p>
          <button type="button" className="mpv1-btn mpv1-btn-outline" onClick={() => void load()}>
            重新載入
          </button>
        </div>
      </BillingShell>
    );
  }

  const effectivePlan = entitlements?.effective_plan_code || "free";
  const status = subscription?.status || "inactive";
  const isActive = ACTIVE_STATUSES.has(status);

  return (
    <BillingShell>
      {notice ? (
        <div className="mpv1-card" role="status">
          <p>{notice}</p>
        </div>
      ) : null}

      <section className="mpv1-card" data-classification="LIVE_MEMBER_DB" data-testid="current-subscription">
        <h2 className="mpv1-card-title">目前訂閱</h2>
        <p>
          方案：<strong>{effectivePlan.toUpperCase()}</strong>
        </p>
        <p>
          狀態：<strong>{statusLabel(status)}</strong>
        </p>
        {status === "past_due" ? (
          <p className="mpv1-auth-error" role="alert">
            付款出現問題，付費功能已暫時停用。請更新付款方式以恢復。
          </p>
        ) : null}
        {subscription?.cancel_at_period_end ? (
          <p className="mpv1-muted">已排定於本期結束後取消。</p>
        ) : null}
        <p className="mpv1-muted">
          目前權益：
          {entitlements && entitlements.entitlements.length
            ? entitlements.entitlements.map(entitlementLabel).join("、")
            : "沒有可用權益"}
        </p>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
          {isActive ? (
            <>
              <button type="button" className="mpv1-btn mpv1-btn-outline" onClick={() => void onPortal()}>
                管理付款方式
              </button>
              {!subscription?.cancel_at_period_end ? (
                <button type="button" className="mpv1-btn mpv1-btn-outline" onClick={() => void onCancel()}>
                  取消訂閱
                </button>
              ) : null}
            </>
          ) : null}
        </div>
      </section>

      <section className="mpv1-card" data-testid="usage-summary">
        <h2 className="mpv1-card-title">使用額度</h2>
        {usageError ? (
          <p className="mpv1-muted" role="status">
            使用額度目前無法取得，請稍後再試。
          </p>
        ) : usage ? (
          (() => {
            const metered = usage.quotas.filter((q) => q.quota_type === "consumable" && q.limit > 0);
            if (!metered.length) {
              return <p className="mpv1-muted">目前方案沒有計量額度。</p>;
            }
            return (
              <div style={{ display: "grid", gap: "0.75rem" }}>
                {metered.map((q) => {
                  const pct = q.limit > 0 ? Math.min(100, Math.round((q.used / q.limit) * 100)) : 0;
                  return (
                    <div key={q.quota_code} data-testid={`usage-${q.quota_code}`}>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
                        <span>{q.label}</span>
                        <span aria-label={`${q.used} / ${q.limit}`}>
                          {q.used} / {q.limit}（剩餘 {q.remaining}）
                        </span>
                      </div>
                      <div
                        className="mpv1-usage-bar"
                        role="progressbar"
                        aria-valuenow={q.used}
                        aria-valuemin={0}
                        aria-valuemax={q.limit}
                        style={{ background: "var(--mp-border,#243)", borderRadius: "6px", height: "8px", overflow: "hidden", marginTop: "0.25rem" }}
                      >
                        <div style={{ width: `${pct}%`, height: "100%", background: q.remaining === 0 ? "#c0392b" : "#2d7" }} />
                      </div>
                      {q.remaining === 0 ? (
                        <p className="mpv1-muted" style={{ marginTop: "0.25rem" }}>
                          本期額度已用完。
                        </p>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            );
          })()
        ) : (
          <p className="mpv1-muted" aria-busy="true">
            載入使用額度中…
          </p>
        )}
      </section>

      <div className="mpv1-plan-grid" data-classification="STATIC_PRODUCT_CONFIG">
        {plans.map((plan) => {
          const current = plan.code === effectivePlan;
          const selfService = isSelfServicePlan(plan.code);
          return (
            <article className={`mpv1-plan${current ? " is-hot" : ""}`} key={plan.code} data-testid={`plan-${plan.code}`}>
              <h2>{plan.display_name}</h2>
              <p className="mpv1-muted">{plan.description || planTagline(plan.code)}</p>
              {current ? (
                <span className="mpv1-chip" data-testid={`current-${plan.code}`}>
                  目前方案
                </span>
              ) : plan.code === "enterprise" ? (
                // Enterprise is contact-sales, not self-service. No hardcoded
                // email/domain until branding + contact are configured.
                <button type="button" className="mpv1-btn mpv1-btn-outline" disabled data-testid="enterprise-contact">
                  企業方案即將開放
                </button>
              ) : selfService ? (
                <button
                  type="button"
                  className="mpv1-btn mpv1-btn-primary"
                  disabled={busyPlan === plan.code}
                  onClick={() => void onUpgrade(plan.code)}
                  data-testid={`upgrade-${plan.code}`}
                >
                  {busyPlan === plan.code ? "前往結帳…" : "升級"}
                </button>
              ) : (
                <button type="button" className="mpv1-btn mpv1-btn-outline" disabled>
                  免費方案
                </button>
              )}
            </article>
          );
        })}
      </div>
    </BillingShell>
  );
}

function BillingShell({ children }: { children: ReactNode }) {
  return (
    <>
      <div className="mpv1-page-head">
        <div>
          <h1 className="mpv1-page-title">會員方案與帳務</h1>
          <p className="mpv1-page-sub">方案與權益以後端帳務系統為準。</p>
        </div>
      </div>
      {children}
    </>
  );
}

// ---------------------------------------------------------------------------
// Stripe redirect return pages
// ---------------------------------------------------------------------------

export function BillingSuccessPage() {
  const navigate = useNavigate();
  const [state, setState] = useState<"confirming" | "active" | "pending">("confirming");

  useEffect(() => {
    let active = true;
    let attempts = 0;
    const maxAttempts = 15; // ~30s at 2s interval

    async function poll() {
      attempts += 1;
      try {
        const { subscription } = await getBillingSubscription();
        if (!active) return;
        if (ACTIVE_STATUSES.has(subscription.status)) {
          setState("active");
          return;
        }
      } catch {
        // ignore transient errors; keep polling
      }
      if (!active) return;
      if (attempts >= maxAttempts) {
        setState("pending");
        return;
      }
      window.setTimeout(() => void poll(), 2000);
    }
    void poll();
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="mpv1-auth-shell">
      <MarketingHeader />
      <div className="mpv1-page-pad">
        <div className="mpv1-auth-card" style={{ margin: "2rem auto" }}>
          {state === "confirming" ? (
            <>
              <h2>正在確認你的訂閱…</h2>
              {/* Success is NOT assumed from the redirect. We wait for the
                  verified backend/webhook state before showing anything. */}
              <p className="mpv1-sub" aria-busy="true">
                我們正在向帳務系統確認付款結果，請稍候。
              </p>
            </>
          ) : state === "active" ? (
            <>
              <h2>訂閱已啟用</h2>
              <p className="mpv1-sub">你的方案已生效，付費功能已解鎖。</p>
              <button
                type="button"
                className="mpv1-btn mpv1-btn-primary mpv1-btn-block"
                onClick={() => navigate("/app/membership")}
              >
                前往會員中心
              </button>
            </>
          ) : (
            <>
              <h2>處理中</h2>
              <p className="mpv1-sub">
                付款可能仍在處理。訂閱會在帳務系統確認後自動生效，你可以稍後回到會員中心查看。
              </p>
              <Link className="mpv1-btn mpv1-btn-outline mpv1-btn-block" to="/app/membership">
                前往會員中心
              </Link>
            </>
          )}
        </div>
      </div>
      <AuthFooter />
    </div>
  );
}

export function BillingCancelPage() {
  // Returning from a canceled checkout changes NOTHING: no upgrade, no
  // downgrade, no DB write. Purely informational.
  return (
    <div className="mpv1-auth-shell">
      <MarketingHeader />
      <div className="mpv1-page-pad">
        <div className="mpv1-auth-card" style={{ margin: "2rem auto" }}>
          <h2>此次付款沒有完成</h2>
          <p className="mpv1-sub">你的訂閱沒有任何變更。你可以隨時再回到會員中心選擇方案。</p>
          <Link className="mpv1-btn mpv1-btn-primary mpv1-btn-block" to="/app/membership">
            返回會員中心
          </Link>
        </div>
      </div>
      <AuthFooter />
    </div>
  );
}
