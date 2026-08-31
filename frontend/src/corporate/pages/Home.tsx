import { lazy, Suspense } from "react";
import { Link } from "react-router-dom";
import { getContent, getHome } from "../api/client";
import { energyOf, regimeOf, useMarket } from "../context/MarketContext";
import { HeroFallback } from "../components/hero/HeroFallback";
import { LiveShowcase } from "../components/LiveShowcase";
import { MarketStructureScene } from "../components/scenes/MarketStructureScene";
import { IntelligenceEngineScene } from "../components/scenes/IntelligenceEngineScene";
import { PersonalEnterpriseBranch } from "../components/scenes/PersonalEnterpriseBranch";
import { CapabilityScene } from "../components/scenes/CapabilityScene";
import { TrustLayer } from "../components/scenes/TrustLayer";
import { useResource, useReveal } from "../hooks/useCorporate";
import { reducedMotion } from "../hooks/useScrollScene";
import { useSeo } from "../hooks/useSeo";
import { track } from "../lib/analytics";
import type { ContentEnvelope, HomeContent, HomeScene } from "../types";

// Animated hero is lazy-loaded AFTER first meaningful content (keeps initial JS lean).
const IntelligenceHero = lazy(() => import("../components/hero/IntelligenceHero"));

const REGIME_TEXT: Record<string, string> = {
  RISK_ON: "Risk-On", RISK_OFF: "Risk-Off", NEUTRAL: "Neutral",
};

function scene(scenes: HomeScene[] | undefined, id: string): HomeScene | undefined {
  return (scenes ?? []).find((s) => s.id === id);
}

function Hero({ home }: { home?: HomeContent }) {
  const market = useMarket();
  const regime = regimeOf(market);
  const energy = energyOf(market);
  const hero = scene(home?.scenes, "hero");
  const reduce = reducedMotion();

  const state = market.status === "READY" ? (regime ?? "NEUTRAL") : market.status === "LOADING" ? "LOADING" : "UNAVAILABLE";
  const statusText =
    market.status === "READY"
      ? `Live market regime · ${regime ? REGIME_TEXT[regime] : "unavailable"}`
      : market.status === "LOADING"
        ? "Connecting to live market…"
        : "Live market temporarily unavailable";

  return (
    <header className="corp-hero" data-testid="corp-hero">
      {reduce ? (
        <HeroFallback />
      ) : (
        <Suspense fallback={<HeroFallback />}>
          <IntelligenceHero energy={energy} regime={regime} available={market.status === "READY"} />
        </Suspense>
      )}
      <div className="corp-hero-veil" aria-hidden />
      <div className="corp-hero-inner">
        <div className="corp-hero-kicker">{hero?.kicker ?? "MARKET INTELLIGENCE"}</div>
        <h1 className="corp-hero-title">{hero?.title ?? "看見市場結構，而非只有價格"}</h1>
        <p className="corp-hero-sub">
          {hero?.subtitle ?? "A real-data market intelligence platform. Price is only the surface."}
        </p>
        <div className="corp-hero-cta">
          <Link to={hero?.primary_cta?.to ?? "/products"} className="corp-btn" onClick={() => track("cta_primary", "hero")}>
            {hero?.primary_cta?.label ?? "探索平台 / Explore"}
          </Link>
          <Link to="/security" className="corp-btn-ghost">安全與信任 / Trust</Link>
        </div>
        <div className="corp-hero-status" data-state={state} data-testid="hero-status" role="status" aria-live="polite">
          <span className="corp-state-dot" />
          {statusText}
        </div>
      </div>
    </header>
  );
}

function ShowcaseSection({ home }: { home?: HomeContent }) {
  const s = scene(home?.scenes, "showcase");
  const { ref, shown } = useReveal<HTMLDivElement>();
  return (
    <section className="corp-section" aria-labelledby="corp-showcase-h">
      <div className="corp-section-inner" ref={ref}>
        <div className={`corp-reveal ${shown ? "is-shown" : ""}`} style={{ ["--p" as string]: shown ? "1" : "0" }}>
          <div className="corp-eyebrow">LIVE MARKET</div>
          <h2 className="corp-h2" id="corp-showcase-h">{s?.title ?? "Live Market Intelligence"}</h2>
          <p className="corp-lead">
            {s?.body ?? "Real BTC / ETH / SOL public data with source, freshness and provenance on every value."}
          </p>
        </div>
        <div style={{ marginTop: "1.75rem" }}>
          <LiveShowcase />
        </div>
      </div>
    </section>
  );
}

function ClosingCta({ home }: { home?: HomeContent }) {
  const v = scene(home?.scenes, "vision");
  return (
    <section className="corp-section" aria-labelledby="corp-cta-h">
      <div className="corp-section-inner" style={{ textAlign: "center" }}>
        <h2 className="corp-h2" id="corp-cta-h" style={{ margin: "0 auto 0.7rem" }}>
          {v?.title ?? "A global intelligence platform"}
        </h2>
        <p className="corp-lead" style={{ margin: "0 auto 1.5rem" }}>
          {v?.body ?? "Built to scale across markets, surfaces and teams."}
        </p>
        <div className="corp-hero-cta" style={{ justifyContent: "center" }}>
          <Link to="/products" className="corp-btn" onClick={() => track("cta_primary", "closing")}>
            開始使用 / Get started
          </Link>
          <Link to="/contact" className="corp-btn-ghost">聯絡我們 / Contact</Link>
        </div>
      </div>
    </section>
  );
}

export function Home() {
  const homeState = useResource<ContentEnvelope<HomeContent>>(getHome, []);
  const seoState = useResource<ContentEnvelope<{ default?: { title?: string; description?: string; robots?: string } }>>(
    () => getContent("seo"),
    [],
  );
  const home = homeState.status === "READY" ? homeState.data.data : undefined;
  const seo = seoState.status === "READY" ? seoState.data.data?.default : undefined;

  useSeo({
    title: seo?.title ?? "NEXUS · Market Intelligence Platform",
    description: seo?.description ?? "A real-data market intelligence platform.",
    path: "/",
    robots: seo?.robots ?? "index,follow",
    jsonLd: {
      "@context": "https://schema.org",
      "@type": "Organization",
      name: "NEXUS",
      description: seo?.description ?? "A real-data market intelligence platform.",
    },
  });

  return (
    <div className="corp-home">
      <Hero home={home} />
      <MarketStructureScene />
      <ShowcaseSection home={home} />
      <IntelligenceEngineScene />
      <PersonalEnterpriseBranch />
      <CapabilityScene />
      <TrustLayer />
      <ClosingCta home={home} />
    </div>
  );
}
