import { getContent, getHome } from "../api/client";
import { FlagshipHero } from "../components/hero/FlagshipHero";
import { MarketStrip } from "../components/product/MarketStrip";
import { PriceVsIntelligence } from "../components/product/PriceVsIntelligence";
import { CommandCenter } from "../components/product/CommandCenter";
import { AttentionPanel } from "../components/product/AttentionPanel";
import { IntelligenceFeed } from "../components/product/IntelligenceFeed";
import { MarketBrief } from "../components/product/MarketBrief";
import { HowItWorks, ProductChoice, TrustFlagship, ClosingCta } from "../components/product/StaticSections";
import { useResource } from "../hooks/useCorporate";
import { useSeo } from "../hooks/useSeo";
import type { ContentEnvelope, HomeContent, HomeScene } from "../types";

function scene(scenes: HomeScene[] | undefined, id: string): HomeScene | undefined {
  return (scenes ?? []).find((s) => s.id === id);
}

function SectionHead({ eyebrow, title, en, sub }: { eyebrow: string; title: string; en?: string; sub?: string }) {
  return (
    <div className="corp-fs-head">
      <div>
        <div className="corp-fs-eyebrow">{eyebrow}</div>
        <h2 className="corp-fs-h2">{title}{en ? <span className="en">{en}</span> : null}</h2>
        {sub ? <p className="corp-fs-sub">{sub}</p> : null}
      </div>
    </div>
  );
}

export function Home() {
  const homeState = useResource<ContentEnvelope<HomeContent>>(getHome, []);
  const seoState = useResource<ContentEnvelope<{ default?: { title?: string; description?: string; robots?: string } }>>(
    () => getContent("seo"), [],
  );
  const home = homeState.status === "READY" ? homeState.data.data : undefined;
  const seo = seoState.status === "READY" ? seoState.data.data?.default : undefined;

  useSeo({
    title: seo?.title ?? "NEXUS · 市場情報平台",
    description: seo?.description ?? "把即時行情、波動、結構與風險，整理成可以直接判讀的市場情報層。",
    path: "/",
    robots: seo?.robots ?? "index,follow",
    jsonLd: { "@context": "https://schema.org", "@type": "Organization", name: "NEXUS",
      description: seo?.description ?? "市場情報平台" },
  });

  return (
    <div className="corp-fs corp-home">
      {/* 01 HERO */}
      <FlagshipHero hero={scene(home?.scenes, "hero")} />

      {/* 02 LIVE MARKET STRIP */}
      <section className="corp-fs-section tight" aria-label="即時行情">
        <div className="corp-fs-inner"><MarketStrip /></div>
      </section>

      {/* 03 PRICE VS INTELLIGENCE */}
      <section className="corp-fs-section corp-fs-band" aria-labelledby="fs-pvi">
        <div className="corp-fs-inner">
          <SectionHead eyebrow="PRICE VS INTELLIGENCE" title="價格只是開始" en="Price is only the beginning"
            sub="價格告訴你發生了什麼；情報告訴你現在該注意什麼。" />
          <div id="fs-pvi"><PriceVsIntelligence /></div>
        </div>
      </section>

      {/* 04 MARKET COMMAND CENTER */}
      <section className="corp-fs-section" aria-labelledby="fs-cc">
        <div className="corp-fs-inner wide">
          <SectionHead eyebrow="COMMAND CENTER" title="市場情報指揮中心" en="One screen, the whole market"
            sub="行情、情報與風險，集中在一個即時面板。" />
          <div id="fs-cc"><CommandCenter /></div>
        </div>
      </section>

      {/* 05 OPPORTUNITY / RISK */}
      <section className="corp-fs-section corp-fs-band" aria-labelledby="fs-attn">
        <div className="corp-fs-inner">
          <SectionHead eyebrow="WHAT NEEDS ATTENTION" title="現在，什麼值得注意" en="Attention & risk"
            sub="依即時波動與區間，標示每個資產的關注程度。" />
          <div id="fs-attn"><AttentionPanel /></div>
        </div>
      </section>

      {/* 06 INTELLIGENCE FEED */}
      <section className="corp-fs-section" aria-labelledby="fs-feed">
        <div className="corp-fs-inner">
          <SectionHead eyebrow="INTELLIGENCE FEED" title="市場情報事件流" en="Real, backend-computed events"
            sub="市場狀態與波動的變化，即時記錄成事件。" />
          <div id="fs-feed"><IntelligenceFeed /></div>
        </div>
      </section>

      {/* 07 AI MARKET BRIEF */}
      <section className="corp-fs-section corp-fs-band" aria-labelledby="fs-brief">
        <div className="corp-fs-inner">
          <SectionHead eyebrow="MARKET BRIEF" title="一段話，看懂目前市場" en="Deterministic market brief"
            sub="由後端規則生成的市場簡報，聚焦重點與風險。" />
          <div id="fs-brief"><MarketBrief /></div>
        </div>
      </section>

      {/* 08 HOW IT WORKS */}
      <HowItWorks />

      {/* 09 PERSONAL / ENTERPRISE */}
      <ProductChoice />

      {/* 10 TRUST */}
      <TrustFlagship />

      {/* 11 CTA */}
      <ClosingCta />
    </div>
  );
}
