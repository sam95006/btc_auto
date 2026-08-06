import { Link, Navigate } from "react-router-dom";
import { useMemo, useState } from "react";
import { UiDensityToggle } from "../../member/UiDensityToggle";
import {
  isPreviewEntitlementReviewAvailable,
  previewEntitlementOverrideAvailableInProd,
  previewFounderCapabilityCount,
} from "../../member/previewEntitlementReview";
import {
  loadPreviewReviewDensity,
  PREVIEW_PLAN_LABELS,
  PREVIEW_PLANS,
  resetPreviewReviewState,
  savePreviewReviewDensity,
  savePreviewReviewPlan,
} from "../../member/previewMembershipReviewState";
import { usePublicEntitlements } from "../../member/public_entitlements_v18_2";
import type { PublicPlan } from "../../member/public_entitlements_v18_2/types";
import type { UiDensity } from "../../member/uiDensityPrefs";
import { useRuntimeSnapshot, runtimeHonestyLabel } from "../../member/runtime_snapshot";
import { MEMBER_SURFACE_V18_2_1_FLAG } from "../../member/memberSurfaceV1821Flag";

const BUILD_COMMIT =
  import.meta.env.VITE_BUILD_COMMIT?.trim() || import.meta.env.MODE || "dev";

const ROUTE_SHORTCUTS = [
  { to: "/overview", label: "總覽" },
  { to: "/opportunities", label: "機會" },
  { to: "/scanner", label: "掃描器" },
  { to: "/alerts", label: "警報" },
  { to: "/intelligence", label: "情報" },
  { to: "/account", label: "帳戶" },
] as const;

function previewQuerySuffix(): string {
  return `?${MEMBER_SURFACE_V18_2_1_FLAG}=1`;
}

function MembershipReviewBlocked() {
  return (
    <div className="page-stack nx-membership-review" data-testid="membership-review-blocked">
      <section className="nx-card" role="alert">
        <h1>Membership review unavailable</h1>
        <p className="muted">
          Preview entitlement review requires a preview build with{" "}
          <code>VITE_PREVIEW_ENTITLEMENT_REVIEW=true</code> and member surface v18.2.1 enabled.
        </p>
        <p className="muted sm">
          preview_entitlement_override_available_in_prod={" "}
          {String(previewEntitlementOverrideAvailableInProd())}
        </p>
        <Link to="/opportunities">Return to opportunities</Link>
      </section>
    </div>
  );
}

export function MembershipEntitlementReviewPage() {
  if (!isPreviewEntitlementReviewAvailable()) {
    return <MembershipReviewBlocked />;
  }

  return <MembershipEntitlementReviewPanel />;
}

function MembershipEntitlementReviewPanel() {
  const [plan, setPlan] = useState<PublicPlan>(() => {
    try {
      const v = sessionStorage.getItem("nexus_preview_entitlement_review_plan_v1822");
      if (v && PREVIEW_PLANS.includes(v as PublicPlan)) return v as PublicPlan;
    } catch {
      /* ignore */
    }
    return "VISITOR";
  });
  const [density, setDensity] = useState<UiDensity>(() => loadPreviewReviewDensity());
  const { dto, loading, error } = usePublicEntitlements(plan);
  const runtime = useRuntimeSnapshot();

  const dataStateBadge = useMemo(() => {
    if (runtime.snapshot) {
      return runtimeHonestyLabel(runtime.snapshot);
    }
    if (runtime.loading) return "LOADING";
    return "UNAVAILABLE";
  }, [runtime.loading, runtime.snapshot]);

  const onPlan = (p: PublicPlan) => {
    setPlan(p);
    savePreviewReviewPlan(p);
  };

  const onDensity = (d: UiDensity) => {
    setDensity(d);
    savePreviewReviewDensity(d);
  };

  const onReset = () => {
    resetPreviewReviewState();
    setPlan("VISITOR");
    setDensity("SIMPLE");
  };

  const capPreview = dto?.capabilities?.slice(0, 12) ?? [];

  return (
    <div className="page-stack nx-membership-review" data-testid="membership-entitlement-review">
      <header className="nx-review-hero">
        <div className="nx-review-badges" role="status">
          <span className="tag tag-warn">PREVIEW ONLY</span>
          <span className="tag">NO LIVE TRADING</span>
          <span className="tag">NO BILLING</span>
          <span className="tag mono sm" data-testid="review-build-commit">
            build {BUILD_COMMIT}
          </span>
          <span className="tag" data-testid="review-data-state" data-state={dataStateBadge}>
            {dataStateBadge}
          </span>
        </div>
        <h1>Membership entitlement review</h1>
        <p className="muted section-lede">
          預覽環境方案與顯示模式切換 · 不寫入資料庫 · founder capabilities={" "}
          {previewFounderCapabilityCount()}
        </p>
      </header>

      <section className="nx-card" aria-labelledby="review-plan-heading">
        <h2 id="review-plan-heading">方案 Profile</h2>
        <div className="nx-review-plan-row" role="group" aria-label="Preview plan">
          {PREVIEW_PLANS.map((p) => (
            <button
              key={p}
              type="button"
              className={plan === p ? "active" : undefined}
              aria-pressed={plan === p}
              data-testid={`review-plan-${p}`}
              onClick={() => onPlan(p)}
            >
              {PREVIEW_PLAN_LABELS[p]}
              <span className="muted sm"> ({p})</span>
            </button>
          ))}
        </div>
        <div className="nx-review-mode-row">
          <span className="nav-label">顯示模式</span>
          <UiDensityToggle density={density} onDensityChange={onDensity} />
        </div>
      </section>

      <section className="nx-card" aria-labelledby="review-entitlement-heading">
        <h2 id="review-entitlement-heading">Entitlements (read-only API)</h2>
        {dto ? (
          <dl className="nx-review-dl" data-testid="review-entitlement-dto">
            <div>
              <dt>plan</dt>
              <dd>{dto.plan}</dd>
            </div>
            <div>
              <dt>capabilities</dt>
              <dd>{dto.capabilities.length}</dd>
            </div>
            <div>
              <dt>production_billing</dt>
              <dd>{String(dto.production_billing)}</dd>
            </div>
            <div>
              <dt>sample</dt>
              <dd className="mono sm">{capPreview.join(", ")}{dto.capabilities.length > 12 ? "…" : ""}</dd>
            </div>
          </dl>
        ) : null}
        <p className="muted sm" data-testid="review-selected-plan">
          Selected preview plan: {plan} ({PREVIEW_PLAN_LABELS[plan]})
        </p>
        {loading ? <p className="muted">Loading…</p> : null}
        {error ? (
          <p className="muted" role="alert" data-testid="review-entitlement-error">
            {error} · static preview (no backend)
          </p>
        ) : null}
        {!dto && !loading ? (
          <dl className="nx-review-dl" data-testid="review-entitlement-dto">
            <div>
              <dt>plan</dt>
              <dd>{plan}</dd>
            </div>
            <div>
              <dt>source</dt>
              <dd>preview_session_only</dd>
            </div>
          </dl>
        ) : null}
      </section>

      <section className="nx-card" aria-labelledby="review-routes-heading">
        <h2 id="review-routes-heading">Route shortcuts</h2>
        <nav className="nx-review-shortcuts" aria-label="Member routes">
          {ROUTE_SHORTCUTS.map((r) => (
            <Link key={r.to} to={`${r.to}${previewQuerySuffix()}`} data-testid={`review-route-${r.to.slice(1)}`}>
              {r.label}
            </Link>
          ))}
          <Link to={`/preview/v18_2_1/review`} data-testid="review-route-preview-path">
            /preview/v18_2_1/review
          </Link>
        </nav>
      </section>

      <section className="nx-card">
        <button type="button" className="nx-review-reset" data-testid="review-reset-state" onClick={onReset}>
          Reset preview state
        </button>
      </section>

      <p className="muted sm">
        Current preview mode: <strong>{density}</strong> · Selected: {PREVIEW_PLAN_LABELS[plan]}
      </p>
    </div>
  );
}

/** Guard wrapper for mistaken prod deep-links without review build. */
export function MembershipReviewEntryGuard() {
  if (!isPreviewEntitlementReviewAvailable()) {
    return <Navigate to="/opportunities" replace />;
  }
  return <MembershipEntitlementReviewPage />;
}
