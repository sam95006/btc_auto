import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { MemberPageChrome } from "../../member/MemberPageChrome";
import {
  MemberFirstScreenPro,
  MemberFirstScreenSimple,
} from "../../member/MemberFirstScreen";
import { buildDemoFirstScreen } from "../../member/firstScreenAnswers";
import {
  loadMemberViewMode,
  saveMemberViewMode,
  type MemberViewMode,
} from "../../member/memberViewPrefs";
import { MEMBER_NAV } from "../../member/routes";
import type { MemberUxState } from "../../member/uxStates";
import { BoundLiveValue, useLiveBindings } from "../../public_v2_live_binding";

/**
 * PUB2-C Member Home — first screen answers five Decision Integrity questions.
 * Simple / Pro views. States: fresh/stale/degraded/pending/unavailable/blocked/empty/error/loading.
 * PUB2-B live bindings retained as a mapped live strip (lineage, no fabricated LIVE).
 * Visual parity with external reference is NOT claimed without screenshots.
 */
export function MemberHomePage() {
  const [view, setView] = useState<MemberViewMode>(() => loadMemberViewMode());
  const [shellOverride, setShellOverride] = useState<MemberUxState | "demo">("demo");
  const { slot, loading } = useLiveBindings();
  const hero = slot("home.hero_decision_summary", "posture");
  const market = slot("home.market_context_card", "btc");
  const fresh = slot("home.freshness_chip", "freshness");
  const risk = slot("home.risk_open_chip", "qual");

  useEffect(() => {
    const onView = (e: Event) => {
      const mode = (e as CustomEvent<MemberViewMode>).detail;
      if (mode === "simple" || mode === "pro") setView(mode);
    };
    window.addEventListener("nexus-member-view-mode", onView);
    return () => window.removeEventListener("nexus-member-view-mode", onView);
  }, []);

  const model = useMemo(
    () =>
      buildDemoFirstScreen(shellOverride === "demo" ? undefined : shellOverride),
    [shellOverride],
  );

  const setMode = (mode: MemberViewMode) => {
    setView(mode);
    saveMemberViewMode(mode);
    window.dispatchEvent(new CustomEvent("nexus-member-view-mode", { detail: mode }));
  };

  return (
    <MemberPageChrome
      title="NEXUS Member Home"
      subtitle="Crypto Decision Integrity · first screen answers before any chase impulse"
    >
      <div className="member-view-toggle" role="group" aria-label="Simple or Pro view">
        <button
          type="button"
          className={view === "simple" ? "active" : undefined}
          aria-pressed={view === "simple"}
          onClick={() => setMode("simple")}
        >
          Simple View
        </button>
        <button
          type="button"
          className={view === "pro" ? "active" : undefined}
          aria-pressed={view === "pro"}
          onClick={() => setMode("pro")}
        >
          Pro View
        </button>
      </div>

      {view === "pro" ? (
        <div className="member-state-demo" aria-label="Shell state preview">
          <label htmlFor="member-shell-state">
            Shell state preview (local demo · not LIVE fabrication)
          </label>
          <select
            id="member-shell-state"
            value={shellOverride}
            onChange={(e) =>
              setShellOverride(e.target.value as MemberUxState | "demo")
            }
          >
            <option value="demo">DEMO bound (default)</option>
            <option value="fresh">fresh</option>
            <option value="stale">stale</option>
            <option value="degraded">degraded</option>
            <option value="pending">pending</option>
            <option value="unavailable">unavailable</option>
            <option value="blocked">blocked</option>
            <option value="empty">empty</option>
            <option value="error">error</option>
            <option value="loading">loading</option>
          </select>
        </div>
      ) : null}

      {view === "simple" ? (
        <MemberFirstScreenSimple model={model} />
      ) : (
        <MemberFirstScreenPro model={model} />
      )}

      <section className="member-stat-grid" aria-label="Home live bindings">
        {loading ? <p className="muted">Loading live bindings...</p> : null}
        <BoundLiveValue binding={hero} label="Decision cloud" />
        <BoundLiveValue binding={market} label="BTC last" />
        <BoundLiveValue binding={fresh} label="Freshness" />
        <BoundLiveValue binding={risk} label="Qualification" />
      </section>

      <section className="member-panel" aria-label="Navigate">
        <h2 className="nx-sec-title">Navigate Decision loop</h2>
        <p className="muted sm">
          Market Observation → Evidence → Counter Evidence → Risk → Decision → Thesis Monitor →
          Outcome Review → Decision Memory. No exchange orders from this product.
        </p>
        <ul className="member-link-grid">
          {MEMBER_NAV.map((item) => (
            <li key={item.to}>
              <Link to={item.to}>{item.label}</Link>
            </li>
          ))}
        </ul>
      </section>

      <p className="muted sm member-parity-note" data-testid="member-parity-note">
        Reference URL is visual SoT only and is never loaded at runtime. Visual parity is not claimed
        without Founder-supplied screenshots.
      </p>
    </MemberPageChrome>
  );
}
