import { getContent, getHome } from "../api/client";
import { FlagshipHero } from "../components/hero/FlagshipHero";
import { JobsSection } from "../components/product/JobsSection";
import { LiveProduct } from "../components/product/LiveProduct";
import { ProductChoice, TrustCompact, ClosingCta } from "../components/product/StaticSections";
import { useResource } from "../hooks/useCorporate";
import { LOCALES, useLocale } from "../i18n";
import { useSeo } from "../hooks/useSeo";
import type { ContentEnvelope, HomeContent, HomeScene } from "../types";

function scene(scenes: HomeScene[] | undefined, id: string): HomeScene | undefined {
  return (scenes ?? []).find((s) => s.id === id);
}

/**
 * Simplified homepage — six primary sections, one idea above the fold, one
 * primary CTA. Detail lives inside tabs / drawers / product pages. Business copy
 * is backend/CMS-driven and locale-aware; market data is realtime backend-driven.
 */
export function Home() {
  const { locale } = useLocale();
  const homeState = useResource<ContentEnvelope<HomeContent>>(() => getHome(locale), [locale]);
  const seoState = useResource<ContentEnvelope<{ default?: { title?: string; description?: string; robots?: string } }>>(
    () => getContent("seo", locale), [locale],
  );
  const home = homeState.status === "READY" ? homeState.data.data : undefined;
  const seo = seoState.status === "READY" ? seoState.data.data?.default : undefined;

  const origin = typeof location !== "undefined" ? location.origin : "";
  const hreflang = [
    ...LOCALES.map((l) => ({ hreflang: l, href: `${origin}/?locale=${l}` })),
    { hreflang: "x-default", href: `${origin}/` },
  ];

  useSeo({
    title: seo?.title ?? "NEXUS · 市場情報平台",
    description: seo?.description ?? "把即時行情、波動與風險，整理成可以快速理解的市場情報。",
    path: "/",
    robots: seo?.robots ?? "index,follow",
    hreflang,
    jsonLd: { "@context": "https://schema.org", "@type": "Organization", name: "NEXUS",
      inLanguage: locale, description: seo?.description ?? "市場情報平台" },
  });

  return (
    <div className="corp-fs corp-home">
      {/* 01 Hero */}
      <FlagshipHero hero={scene(home?.scenes, "hero")} />
      {/* 02 What you can do — three jobs */}
      <JobsSection />
      {/* 03 Live product — merged tabs */}
      <LiveProduct />
      {/* 04 Personal / Enterprise */}
      <ProductChoice />
      {/* 05 Trust */}
      <TrustCompact />
      {/* 06 CTA */}
      <ClosingCta />
    </div>
  );
}
