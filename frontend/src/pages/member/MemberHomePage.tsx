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
import { MEMBER_NAV } from "../../member/routes";
import { BoundLiveValue, useLiveBindings } from "../../public_v2_live_binding";

type FunnelVariant =
  | "live_read_only"
  | "fixture_wait"
  | "fixture_long"
  | "stale"
  | "unavailable";

/**
 * PUB18-A member home — Live Funnel + Market Pulse first screen.
 * Read-only. No trade buttons / Founder private fields.
 */
export function MemberHomePage() {
  const t = useT();
  const [view, setView] = useState<MemberViewMode>(() => loadMemberViewMode());
  const [funnelVariant, setFunnelVariant] = useState<FunnelVariant>("live_read_only");
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

  const funnelModel = useMemo(
    () => buildLiveFunnelScreen(funnelVariant),
    [funnelVariant],
  );

  const setMode = (mode: MemberViewMode) => {
    setView(mode);
    saveMemberViewMode(mode);
    window.dispatchEvent(new CustomEvent("nexus-member-view-mode", { detail: mode }));
  };

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
            <option value="fixture_long">FIXTURE · LONG observe</option>
            <option value="stale">STALE</option>
            <option value="unavailable">UNAVAILABLE</option>
          </select>
        </div>
      ) : null}

      <LiveFunnelMarketPulseScreen model={funnelModel} />

      <section className="member-stat-grid" aria-label={t("pages.home.metricsLabel")}>
        {loading ? <p className="muted">Loading live bindings...</p> : null}
        <BoundLiveValue binding={hero} label="Decision cloud" />
        <BoundLiveValue binding={market} label="BTC last" />
        <BoundLiveValue binding={fresh} label="Freshness" />
        <BoundLiveValue binding={risk} label="Qualification" />
      </section>

      <section className="member-panel" aria-label={t("pages.home.navLabel")}>
        <h2 className="nx-sec-title">{t("pages.home.navigate")}</h2>
        <p className="muted sm">
          Live Funnel → Market Pulse → Evidence → Counter Evidence → Risk → Decision → Thesis
          Monitor → Outcome Review. Analysis / Shadow only — no exchange orders, no trade buttons.
        </p>
        <ul className="member-link-grid">
          {MEMBER_NAV.map((item) => (
            <li key={item.to}>
              <Link to={item.to}>{t(item.labelKey)}</Link>
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
