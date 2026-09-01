/**
 * Simplified hero (CORPORATE-4). Answers WHAT / WHY / WHAT NEXT in one glance:
 * localized headline + one sentence + ONE primary CTA + one secondary link on the
 * left; ONE real live intelligence console on the right; a lazy R3F field behind
 * (desktop, non-reduced-motion) with a static fallback + WebGL error boundary.
 * Headline/subtitle come from the backend CMS `home` hero (locale-aware).
 */
import { Component, lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { energyOf, regimeOf, useMarket, useRealtime } from "../../context/MarketContext";
import { reducedMotion } from "../../hooks/useScrollScene";
import { useLocale } from "../../i18n";
import { track } from "../../lib/analytics";
import type { HomeScene } from "../../types";
import { LiveConsole } from "../product/LiveConsole";
import { RealtimePill } from "../product/RealtimePill";
import { HeroFallback } from "./HeroFallback";

const IntelligenceR3F = lazy(() => import("./IntelligenceR3F"));

class HeroBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? this.props.fallback : this.props.children; }
}

function useHeavyOk() {
  const [ok, setOk] = useState(false);
  useEffect(() => { setOk(window.matchMedia("(min-width: 960px)").matches && !reducedMotion()); }, []);
  return ok;
}

export function FlagshipHero({ hero }: { hero?: HomeScene }) {
  const market = useMarket();
  const rt = useRealtime();
  const { t } = useLocale();
  const heavy = useHeavyOk();

  const title = hero?.title ?? t("hero_eyebrow");
  const sub = hero?.subtitle ?? "";

  return (
    <header className="corp-fs-hero" data-testid="corp-hero">
      {heavy ? (
        <HeroBoundary fallback={<HeroFallback />}>
          <Suspense fallback={<HeroFallback />}>
            <IntelligenceR3F energy={energyOf(market)} regime={regimeOf(market)} available={market.status === "READY"} />
          </Suspense>
        </HeroBoundary>
      ) : (
        <HeroFallback />
      )}
      <div className="corp-hero-veil" aria-hidden />
      <div className="corp-fs-hero-grid">
        <div>
          <span className="corp-fs-hero-status">{hero?.kicker ?? t("hero_eyebrow")}</span>
          <h1 className="corp-fs-hero-title">{title}</h1>
          {sub ? <p className="corp-fs-hero-sub">{sub}</p> : null}
          <div className="corp-fs-hero-cta single">
            <Link to="/personal" className="corp-fs-btn" onClick={() => track("cta_primary", "hero")}>{t("cta_start")}</Link>
            <Link to="/products" className="corp-fs-hero-link">{t("cta_view")} →</Link>
          </div>
          <div style={{ marginTop: "1.4rem" }}><RealtimePill rt={rt} /></div>
        </div>
        <div><LiveConsole /></div>
      </div>
    </header>
  );
}
