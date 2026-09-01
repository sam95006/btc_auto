/**
 * Flagship hero — premium split layout. LEFT: status + headline + copy + CTAs +
 * trust line (Chinese-primary). RIGHT: a REAL live market console (backend data).
 * BEHIND: a lazy R3F intelligence field on desktop / non-reduced-motion, a static
 * SVG fallback otherwise. Headline/sub come from the CMS `home` hero (editable).
 */
import { Component, lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { energyOf, regimeOf, useMarket } from "../../context/MarketContext";
import { reducedMotion } from "../../hooks/useScrollScene";
import { track } from "../../lib/analytics";
import type { HomeScene } from "../../types";
import { LiveConsole } from "../product/LiveConsole";
import { HeroFallback } from "./HeroFallback";

const IntelligenceR3F = lazy(() => import("./IntelligenceR3F"));

/** If WebGL is unavailable or the 3D scene throws, fall back to the static hero. */
class HeroBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? this.props.fallback : this.props.children; }
}

function useHeavyOk() {
  const [ok, setOk] = useState(false);
  useEffect(() => {
    const wide = window.matchMedia("(min-width: 900px)").matches;
    setOk(wide && !reducedMotion());
  }, []);
  return ok;
}

export function FlagshipHero({ hero }: { hero?: HomeScene }) {
  const market = useMarket();
  const regime = regimeOf(market);
  const energy = energyOf(market);
  const heavy = useHeavyOk();

  const title = hero?.title ?? "市場很多資料，你不需要全部自己看。";
  const sub = hero?.subtitle ?? "NEXUS 把即時行情、波動、結構與風險，整理成一個可以直接判讀的市場情報層。";

  return (
    <header className="corp-fs-hero" data-testid="corp-hero">
      {heavy ? (
        <HeroBoundary fallback={<HeroFallback />}>
          <Suspense fallback={<HeroFallback />}>
            <IntelligenceR3F energy={energy} regime={regime} available={market.status === "READY"} />
          </Suspense>
        </HeroBoundary>
      ) : (
        <HeroFallback />
      )}
      <div className="corp-hero-veil" aria-hidden />
      <div className="corp-fs-hero-grid">
        <div>
          <span className="corp-fs-hero-status"><span className="corp-fs-live" style={{ letterSpacing: 0 }} />即時市場情報 · Live Market Intelligence</span>
          <h1 className="corp-fs-hero-title">{title}</h1>
          <p className="corp-fs-hero-sub">{sub}</p>
          <div className="corp-fs-hero-cta">
            <Link to="/personal" className="corp-fs-btn" onClick={() => track("cta_primary", "hero")}>進入個人版</Link>
            <Link to="/enterprise" className="corp-fs-btn-ghost" onClick={() => track("cta_enterprise", "hero")}>了解企業版</Link>
          </div>
          <div className="corp-fs-trust">
            <span>後端真實數據</span>
            <span>唯讀情報</span>
            <span>來源可查</span>
          </div>
        </div>
        <div>
          <LiveConsole />
        </div>
      </div>
    </header>
  );
}
