/**
 * "價格 vs 情報" — the price card (what most people see) unfolds into deeper
 * intelligence layers (what NEXUS sees) as the user scrolls. GSAP ScrollTrigger
 * is lazy-imported (kept out of the critical bundle) and fully skipped under
 * reduced motion. All values are backend-provided (primary = BTC); no fabricated
 * OI/CVD/funding — only layers the backend actually computes.
 */
import { useEffect, useRef } from "react";
import { useMarket } from "../../context/MarketContext";
import { reducedMotion } from "../../hooks/useScrollScene";
import { fmtPct, fmtPrice, symOf } from "../../lib/format";

const REGIME_ZH: Record<string, string> = { RISK_ON: "偏多", RISK_OFF: "防禦", NEUTRAL: "中性" };
const VOL_ZH: Record<string, string> = { high: "偏高", moderate: "中等", low: "偏低" };
const RISK_ZH: Record<string, string> = { elevated: "偏高", moderate: "中等", contained: "受控" };

export function PriceVsIntelligence() {
  const m = useMarket();
  const layersRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const root = layersRef.current;
    if (!root) return;
    const items = Array.from(root.querySelectorAll<HTMLElement>(".corp-fs-layer"));
    if (reducedMotion() || items.length === 0) return; // already visible by default
    let cleanup = () => {};
    let cancelled = false;
    (async () => {
      try {
        const gsap = (await import("gsap")).default;
        const { ScrollTrigger } = await import("gsap/ScrollTrigger");
        if (cancelled) return;
        gsap.registerPlugin(ScrollTrigger);
        const tween = gsap.from(items, {
          opacity: 0, y: 16, stagger: 0.1, ease: "power2.out", duration: 0.55,
          scrollTrigger: { trigger: root, start: "top 80%", once: true },
        });
        cleanup = () => { tween.scrollTrigger?.kill(); tween.kill(); };
      } catch {
        /* fail open: layers stay visible */
      }
    })();
    return () => { cancelled = true; cleanup(); };
  }, [m.status]);

  const ready = m.status === "READY";
  const primary = ready ? (m.data.symbols.find((s) => s.symbol === "BTCUSDT") || m.data.symbols[0]) : undefined;
  const regime = ready ? m.data.regime?.value ?? null : null;
  const risk = ready ? m.data.risk?.value ?? null : null;

  const layers = [
    { k: "Volatility 波動", v: primary?.volatility ? VOL_ZH[primary.volatility] : "—", cls: primary?.volatility === "high" ? "warn" : "accent" },
    { k: "24H Range 區間", v: typeof primary?.range_pct === "number" ? `${primary.range_pct.toFixed(2)}%` : "—", cls: "accent" },
    { k: "Regime 市場狀態", v: regime ? REGIME_ZH[regime] : "—", cls: regime === "RISK_OFF" ? "down" : regime === "RISK_ON" ? "up" : "accent" },
    { k: "Risk 風險", v: risk ? RISK_ZH[risk] || risk : "—", cls: risk === "elevated" ? "warn" : "accent" },
    { k: "Freshness 鮮度", v: ready ? m.data.freshness : "—", cls: "accent" },
    { k: "Source 來源", v: ready ? m.data.source : "—", cls: "accent" },
  ];

  return (
    <div className="corp-fs-pvi">
      <div className="corp-fs-pvi-col you">
        <span className="corp-fs-pvi-tag">大多數人看到的</span>
        <div>
          <div style={{ font: "800 0.85rem/1 var(--fs-mono)" }}>{primary ? `${symOf(primary.symbol)} / USDT` : "BTC / USDT"}</div>
          <div className="corp-fs-pvi-price">{ready && primary ? fmtPrice(primary.price) : "—"}</div>
          <div className={`corp-fs-chg ${(primary?.change_24h_percent ?? 0) >= 0 ? "up" : "down"}`} style={{ marginTop: "0.3rem" }}>
            {ready && primary ? `${fmtPct(primary.change_24h_percent)} · 24H` : "—"}
          </div>
        </div>
        <p className="corp-fs-pvi-note">價格告訴你<b>發生了什麼</b>。</p>
      </div>

      <div className="corp-fs-pvi-col" ref={layersRef}>
        <span className="corp-fs-pvi-tag" style={{ color: "var(--fs-accent-2)" }}>NEXUS 看到的</span>
        <div className="corp-fs-layer-list">
          {layers.map((l) => (
            <div className="corp-fs-layer" key={l.k} data-testid="pvi-layer">
              <span className="lk">{l.k}</span>
              <span />
              <span className={`lv ${l.cls}`}>{l.v}</span>
            </div>
          ))}
        </div>
        <p className="corp-fs-pvi-note">情報告訴你<b>現在應該注意什麼</b>。</p>
      </div>
    </div>
  );
}
