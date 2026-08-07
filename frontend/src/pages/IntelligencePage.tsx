import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { newsProvider } from "../market/providers/newsProvider";
import { fearGreedProvider } from "../market/providers/fearGreedProvider";
import { altcoinSeasonProvider } from "../market/providers/altcoinSeasonProvider";
import { statusTag, type ParityMetric } from "../market/parityContracts";
import { useMarketScannerOverview } from "../market/useMarketScanner";
import { useMarketAnomalies } from "../market/useMarketAnomalies";

/**
 * V18.2.9 Research — denser than consumer Overview.
 * Sub-nav · tables · timeline · comparison · honest pending providers.
 */
export function IntelligencePage() {
  const [news, setNews] = useState<ParityMetric<unknown> | null>(null);
  const [fear, setFear] = useState<ParityMetric<unknown> | null>(null);
  const [alt, setAlt] = useState<ParityMetric<unknown> | null>(null);
  const { status, longs, shorts, events, loading } = useMarketScannerOverview();
  const anomalies = useMarketAnomalies();

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

  const layers: { name: string; status: "live" | "pending"; note: string; tag?: string }[] = [
    { name: "公開市場掃描（價格／OI／Funding）", status: "live", note: "Bybit Mainnet public linear" },
    { name: "市場異動雷達", status: "live", note: "讀取中異常與證據欄位" },
    { name: "版塊動能", status: "live", note: "Sector performance overlay" },
    {
      name: "News",
      status: "pending",
      note: news?.coverageNote || "UNAVAILABLE_PROVIDER_PENDING",
      tag: news ? statusTag(news.status) : undefined,
    },
    {
      name: "Fear & Greed",
      status: "pending",
      note: fear?.coverageNote || "UNAVAILABLE_PROVIDER_PENDING",
      tag: fear ? statusTag(fear.status) : undefined,
    },
    {
      name: "Altcoin Season",
      status: "pending",
      note: alt?.coverageNote || "UNAVAILABLE_PROVIDER_PENDING",
      tag: alt ? statusTag(alt.status) : undefined,
    },
    { name: "Macro", status: "pending", note: "UNAVAILABLE_PROVIDER_PENDING" },
    { name: "On-chain", status: "pending", note: "UNAVAILABLE_PROVIDER_PENDING" },
  ];

  const compareRows = [...longs, ...shorts]
    .slice(0, 12)
    .map((c) => ({
      symbol: c.symbol.replace("USDT", ""),
      href: `/market/${c.symbol}`,
      stage: c.stage,
      risk: c.riskScore == null ? "—" : Math.round(c.riskScore),
      opp: c.opportunityScore == null ? "—" : Math.round(c.opportunityScore),
      funding: c.fundingRate == null ? "—" : `${(c.fundingRate * 100).toFixed(4)}%`,
      oi: c.oiChange5mPct == null ? "—" : `${c.oiChange5mPct > 0 ? "+" : ""}${c.oiChange5mPct.toFixed(2)}%`,
    }));

  const timeline = [
    ...anomalies.slice(0, 8).map((a) => ({
      id: a.id,
      text: `${a.symbol.replace("USDT", "")} · ${a.title}`,
      ts: a.lastSeenAt || a.observedAt,
    })),
    ...events.slice(0, 8).map((e) => ({
      id: e.id,
      text: `${e.symbol.replace("USDT", "")} · ${e.explanation}`,
      ts: e.timestamp,
    })),
  ]
    .sort((a, b) => (b.ts || 0) - (a.ts || 0))
    .slice(0, 10);

  return (
    <div className="v1829-research" data-testid="research-v1829" data-product-gen="v18_2_9">
      <header className="v1829-panel" style={{ marginBottom: 12 }}>
        <h1 className="v1829-page-title">研究</h1>
        <p className="v1829-page-sub" style={{ marginBottom: 10 }}>
          高密度情報工作區 · 與 Overview 消費者節奏分離 · pending 不捏造
        </p>
        <nav className="v1829-research-subnav" aria-label="研究子導航">
          <span className="is-active">總覽</span>
          <Link to="/scanner">掃描表</Link>
          <Link to="/alerts">事件時間軸</Link>
          <Link to="/opportunities">機會比較</Link>
          <Link to="/scanner">掃描器</Link>
        </nav>
      </header>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1.2fr) minmax(0,0.8fr)", gap: 12 }}>
        <section className="v1829-panel" aria-label="情報層狀態">
          <h2 className="v1829-section-title">情報層</h2>
          <table className="v1829-research-table">
            <thead>
              <tr>
                <th>層級</th>
                <th>狀態</th>
                <th>說明</th>
              </tr>
            </thead>
            <tbody>
              {layers.map((p) => (
                <tr key={p.name}>
                  <td>{p.name}</td>
                  <td>
                    {p.status === "live" ? (
                      <span className="v1829-pill v1829-pill-pos">LIVE</span>
                    ) : (
                      <span className="v1829-pill v1829-pill-warn">
                        {p.tag || "UNAVAILABLE"}
                      </span>
                    )}
                  </td>
                  <td className="muted">{p.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="v1829-panel" aria-label="研究時間軸">
          <h2 className="v1829-section-title">時間軸</h2>
          {timeline.length === 0 ? (
            <p className="muted">{loading ? "載入中…" : "目前無事件"}</p>
          ) : (
            <ul className="v1829-timeline">
              {timeline.map((t) => (
                <li key={t.id}>
                  <span className="dot" aria-hidden />
                  <div>
                    <span style={{ fontSize: "0.875rem" }}>{t.text}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
          <p className="muted" style={{ marginTop: 10, fontSize: "0.8125rem" }}>
            監控 {status?.symbolCount ?? "—"} · Eligible {status?.confirmedCandidates ?? "—"}
          </p>
        </section>
      </div>

      <section className="v1829-panel" style={{ marginTop: 12 }} aria-label="標的比較">
        <h2 className="v1829-section-title">候選比較</h2>
        {compareRows.length === 0 ? (
          <p className="muted">目前沒有可比較候選</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="v1829-research-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>狀態</th>
                  <th>風險</th>
                  <th>機會</th>
                  <th>Funding</th>
                  <th>OI 5m</th>
                </tr>
              </thead>
              <tbody>
                {compareRows.map((r) => (
                  <tr key={r.symbol}>
                    <td>
                      <Link to={r.href} className="mono">
                        {r.symbol}
                      </Link>
                    </td>
                    <td>{r.stage}</td>
                    <td className="mono">{r.risk}</td>
                    <td className="mono">{r.opp}</td>
                    <td className="mono">{r.funding}</td>
                    <td className="mono">{r.oi}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
