import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useT } from "../../i18n";
import { MemberPageChrome } from "../../member/MemberPageChrome";
import {
  LiveFunnelMarketPulseScreen,
  buildLiveFunnelScreen,
} from "../../member/live_funnel";
import {
  loadMemberViewMode,
  saveMemberViewMode,
  type MemberViewMode,
} from "../../member/memberViewPrefs";
import { BoundLiveValue, useLiveBindings } from "../../public_v2_live_binding";
import { useRuntimeSnapshot } from "../../member/runtime_snapshot";

type FunnelVariant =
  | "live_read_only"
  | "fixture_wait"
  | "fixture_long"
  | "stale"
  | "unavailable";

/**
 * V18.2 simplified overview — Simple default; Pro expands diagnostics.
 * Read-only. No trade buttons / Founder private fields.
 */
export function MemberHomePage() {
  const t = useT();
  const [view, setView] = useState<MemberViewMode>(() => loadMemberViewMode());
  const [funnelVariant, setFunnelVariant] = useState<FunnelVariant>("live_read_only");
  const { slot, loading } = useLiveBindings();
  const runtime = useRuntimeSnapshot();
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

  const fallbackModel = useMemo(
    () => buildLiveFunnelScreen(funnelVariant),
    [funnelVariant],
  );

  const funnelModel = runtime.model ?? fallbackModel;
  const runtimeSnap = runtime.snapshot;

  const setMode = (mode: MemberViewMode) => {
    setView(mode);
    saveMemberViewMode(mode);
    window.dispatchEvent(new CustomEvent("nexus-member-view-mode", { detail: mode }));
  };

  const eligibleRaw = runtimeSnap?.universe_funnel?.display?.eligible;
  const eligibleZero = eligibleRaw === "0" || String(eligibleRaw ?? "") === "0";

  return (
    <MemberPageChrome titleKey="pages.home.title" subtitleKey="pages.home.subtitle">
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
        <section
          className="member-runtime-status"
          aria-label="Runtime live binding status"
          data-testid="runtime-live-binding-status"
          data-runtime-state={runtimeSnap?.runtime_state || "UNAVAILABLE"}
          data-live-view={runtimeSnap?.is_live_view ? "true" : "false"}
          data-chrome={funnelModel.chromeLabel}
        >
          <header className="member-runtime-status-head">
            <h3>Runtime status</h3>
            <span className="member-chip" data-testid="runtime-state-chip">
              {runtimeSnap?.runtime_state || (runtime.loading ? "LOADING" : "UNAVAILABLE")}
            </span>
            <span className="member-chip" data-testid="runtime-chrome-chip">
              {funnelModel.chromeLabel}
            </span>
          </header>
          <ul className="member-runtime-status-grid">
            <li>
              <span className="muted">Eligible</span>
              <strong>{runtimeSnap?.universe_funnel?.display?.eligible ?? "UNAVAILABLE"}</strong>
            </li>
            <li>
              <span className="muted">Data Trust / freshness</span>
              <strong>{runtimeSnap?.data_freshness || "UNAVAILABLE"}</strong>
            </li>
            <li>
              <span className="muted">actual_ordered / actual_filled</span>
              <strong data-testid="runtime-actual-flags">false / false</strong>
            </li>
          </ul>
          {runtime.error ? (
            <p className="muted sm" data-testid="runtime-bind-error">
              Runtime binder: {runtime.error} — showing honest fallback (not fabricated Live).
            </p>
          ) : null}
          {!runtime.loading && runtimeSnap && !runtimeSnap.is_live_view ? (
            <p className="nx-banner-warn" role="status" data-testid="runtime-not-live-banner">
              Runtime is not Live ({runtimeSnap.display_label}). Prior projection must not be shown
              as Live.
            </p>
          ) : null}
          <div className="member-state-demo" aria-label="Live funnel projection preview">
            <label htmlFor="member-funnel-variant">
              Funnel projection preview (honest labels · never fake Live zeros)
            </label>
            <select
              id="member-funnel-variant"
              value={funnelVariant}
              onChange={(e) => setFunnelVariant(e.target.value as FunnelVariant)}
            >
              <option value="live_read_only">LIVE_READ_ONLY · fail-closed zeros</option>
              <option value="fixture_wait">FIXTURE · WAIT</option>
              <option value="stale">STALE</option>
              <option value="unavailable">UNAVAILABLE</option>
            </select>
          </div>
        </section>
      ) : (
        <section className="member-panel" aria-label="Market status" data-testid="simple-home">
          <h2 className="nx-sec-title">Market status</h2>
          <p data-testid="simple-market-state">
            {runtimeSnap?.display_label || runtimeSnap?.runtime_state || "UNAVAILABLE"}
          </p>
          {eligibleZero ? (
            <p className="nx-banner-warn" role="status" data-testid="no-eligible-opportunities">
              No eligible opportunities currently
            </p>
          ) : null}
        </section>
      )}

      <LiveFunnelMarketPulseScreen model={funnelModel} />

      {view === "pro" ? (
        <section className="member-stat-grid" aria-label={t("pages.home.metricsLabel")}>
          {loading ? <p className="muted">Loading live bindings...</p> : null}
          <BoundLiveValue binding={hero} label="Decision cloud" />
          <BoundLiveValue binding={market} label="BTC last" />
          <BoundLiveValue binding={fresh} label="Freshness" />
          <BoundLiveValue binding={risk} label="Qualification" />
        </section>
      ) : (
        <section className="member-panel" aria-label="Quick links">
          <h2 className="nx-sec-title">Key alerts &amp; AI</h2>
          <p className="muted sm">
            <Link to="/alerts">Alerts</Link> · <Link to="/nex-ai">Ask AI</Link> ·{" "}
            <Link to="/scanner">Scanner funnel</Link>
          </p>
        </section>
      )}
    </MemberPageChrome>
  );
}
