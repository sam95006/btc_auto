import { useEffect, useState } from "react";
import { newsProvider } from "../market/providers/newsProvider";
import { fearGreedProvider } from "../market/providers/fearGreedProvider";
import { altcoinSeasonProvider } from "../market/providers/altcoinSeasonProvider";
import { statusTag, type ParityMetric } from "../market/parityContracts";

/** Phase 6.5 / Product 7.1 — Intelligence with honest provider foundations. */
export function IntelligencePage() {
  const [news, setNews] = useState<ParityMetric<unknown> | null>(null);
  const [fear, setFear] = useState<ParityMetric<unknown> | null>(null);
  const [alt, setAlt] = useState<ParityMetric<unknown> | null>(null);

  useEffect(() => {
    let alive = true;
    void (async () => {
      const [n, f, a] = await Promise.all([
        newsProvider.getHeadlines(5),
        fearGreedProvider.getIndex(),
        altcoinSeasonProvider.getIndex(),
      ]);
      if (!alive) return;
      setNews(n);
      setFear(f);
      setAlt(a);
    })();
    return () => {
      alive = false;
    };
  }, []);

  const layers: { name: string; status: "live" | "pending"; note: string }[] = [
    { name: "公開市場掃描（價格／OI／Funding）", status: "live", note: "Bybit Mainnet public linear" },
    { name: "市場異動雷達", status: "live", note: "讀取中異常與證據欄位" },
    { name: "版塊動能", status: "live", note: "Sector performance overlay" },
    {
      name: "News",
      status: "pending",
      note: news?.coverageNote || "UNAVAILABLE_PROVIDER_PENDING",
    },
    {
      name: "Fear & Greed",
      status: "pending",
      note: fear?.coverageNote || "UNAVAILABLE_PROVIDER_PENDING",
    },
    {
      name: "Altcoin Season",
      status: "pending",
      note: alt?.coverageNote || "UNAVAILABLE_PROVIDER_PENDING",
    },
    { name: "Macro", status: "pending", note: "UNAVAILABLE_PROVIDER_PENDING" },
    { name: "On-chain", status: "pending", note: "UNAVAILABLE_PROVIDER_PENDING" },
    { name: "Stablecoin flow", status: "pending", note: "UNAVAILABLE_PROVIDER_PENDING" },
    { name: "DeFi", status: "pending", note: "UNAVAILABLE_PROVIDER_PENDING" },
    { name: "Social sentiment", status: "pending", note: "UNAVAILABLE_PROVIDER_PENDING" },
    { name: "Geopolitical risk", status: "pending", note: "UNAVAILABLE_PROVIDER_PENDING" },
  ];
  return (
    <div className="page-stack nx-intel-p7">
      <header>
        <h1>情報</h1>
        <p className="muted">
          Extended intelligence — live layers vs Product 7.1 provider foundations（pending 不捏造）.
        </p>
      </header>
      <ul className="nx-intel-pending">
        {layers.map((p) => (
          <li key={p.name}>
            <strong>{p.name}</strong> —{" "}
            {p.status === "live" ? (
              <span className="tag">LIVE</span>
            ) : (
              <span className="tag tag-warn">
                {p.name === "News" && news
                  ? statusTag(news.status)
                  : p.name === "Fear & Greed" && fear
                    ? statusTag(fear.status)
                    : p.name === "Altcoin Season" && alt
                      ? statusTag(alt.status)
                      : "UNAVAILABLE_PROVIDER_PENDING"}
              </span>
            )}
            <span className="muted sm"> · {p.note}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
