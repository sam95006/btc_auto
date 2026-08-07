import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { newsProvider } from "../../market/providers/newsProvider";
import { fearGreedProvider } from "../../market/providers/fearGreedProvider";
import { altcoinSeasonProvider } from "../../market/providers/altcoinSeasonProvider";
import { statusTag, type ParityMetric } from "../../market/parityContracts";
import { useMarketScannerOverview } from "../../market/useMarketScanner";
import { useMarketAnomalies } from "../../market/useMarketAnomalies";
import { STAGE_LABEL_ZH, plainReason } from "../../market/scannerApi";
import { partitionOpportunityCandidates } from "../../market/cryptoOpportunityFilter";
import { usePublicEntitlements } from "../../member/public_entitlements_v18_2";
import { usePreviewReviewPlan } from "../../member/usePreviewReviewPlan";

type FeedItem = {
  id: string;
  title: string;
  excerpt: string;
  kind: "event" | "anomaly" | "candidate" | "layer";
  ts: number;
  symbol?: string;
  locked?: boolean;
};

function agoLabel(ts?: number | null) {
  if (!ts) return "—";
  const sec = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.round(sec / 60)}m`;
  return `${Math.round(sec / 3600)}h`;
}

/**
 * Product V2 Research — feed + reading pane + context drawer.
 * Monetization: locked preview at intent (history), not homepage spam.
 */
export function ResearchPageV2() {
  const [news, setNews] = useState<ParityMetric<unknown> | null>(null);
  const [fear, setFear] = useState<ParityMetric<unknown> | null>(null);
  const [alt, setAlt] = useState<ParityMetric<unknown> | null>(null);
  const { status, longs, shorts, events, loading } = useMarketScannerOverview();
  const anomalies = useMarketAnomalies();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(true);
  const previewPlan = usePreviewReviewPlan("FREE");
  const { dto } = usePublicEntitlements(previewPlan);
  const plan = dto?.plan ?? previewPlan;
  const historyLocked = plan === "FREE";

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

  const { crypto } = partitionOpportunityCandidates([...longs, ...shorts]);

  const feed: FeedItem[] = useMemo(() => {
    const items: FeedItem[] = [];

    items.push({
      id: "layer-scan",
      title: "公開市場掃描層",
      excerpt: "價格／OI／Funding · Bybit Mainnet public linear",
      kind: "layer",
      ts: status?.generatedAt || Date.now(),
    });

    for (const a of anomalies.slice(0, 10)) {
      items.push({
        id: `anom-${a.id}`,
        title: a.title || a.type,
        excerpt: a.explanation || "市場異動",
        kind: "anomaly",
        ts: a.lastSeenAt || a.observedAt || 0,
        symbol: a.symbol,
      });
    }

    for (const e of events.slice(0, 10)) {
      items.push({
        id: `evt-${e.id}`,
        title: `${e.symbol.replace("USDT", "")} · ${e.type || "事件"}`,
        excerpt: e.explanation || "掃描事件",
        kind: "event",
        ts: e.timestamp || 0,
        symbol: e.symbol,
      });
    }

    for (const c of crypto.slice(0, 8)) {
      items.push({
        id: `cand-${c.id}`,
        title: `${c.symbol.replace("USDT", "")} · ${STAGE_LABEL_ZH[c.stage] || c.stage}`,
        excerpt: plainReason(c.reasons?.[0] || "結構觀察", true),
        kind: "candidate",
        ts: c.lastUpdatedAt || 0,
        symbol: c.symbol,
      });
    }

    if (historyLocked) {
      items.push({
        id: "history-lock",
        title: "研究歷史（進階）",
        excerpt: "升級後可回看完整研究軌跡與歸檔筆記",
        kind: "layer",
        ts: 0,
        locked: true,
      });
    }

    items.sort((a, b) => b.ts - a.ts);
    return items;
  }, [anomalies, crypto, events, historyLocked, status?.generatedAt]);

  useEffect(() => {
    if (!selectedId && feed[0]) setSelectedId(feed[0].id);
  }, [feed, selectedId]);

  const selected = feed.find((f) => f.id === selectedId) ?? feed[0] ?? null;

  return (
    <div data-testid="product-v2-research" data-nexus-product-generation="2">
      <header style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-start" }}>
        <div style={{ flex: 1 }}>
          <h1 className="mp2-page-title">研究</h1>
          <p className="mp2-page-sub">閱讀工作區 · 資訊流 + 正文 + 上下文</p>
        </div>
        <button type="button" className="mp2-btn desktop-only" onClick={() => setDrawerOpen((v) => !v)}>
          {drawerOpen ? "收合上下文" : "展開上下文"}
        </button>
      </header>

      <div className="mp2-research">
        <div className="mp2-research-feed" aria-label="研究資訊流">
          <p className="mp2-kicker">資訊流</p>
          {loading && !feed.length ? <p className="muted">載入中…</p> : null}
          {feed.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`mp2-research-item${selected?.id === item.id ? " is-active" : ""}`}
              onClick={() => setSelectedId(item.id)}
            >
              <strong>
                {item.locked ? "🔒 " : ""}
                {item.title}
              </strong>
              <span>
                {item.kind} · {agoLabel(item.ts)}
              </span>
            </button>
          ))}
        </div>

        <article className="mp2-research-read" aria-label="閱讀區">
          {selected?.locked ? (
            <div className="mp2-lock" data-testid="research-history-lock">
              <strong>研究歷史為進階能力</strong>
              目前方案 {plan} 可預覽此意圖；升級後解鎖完整歷史與歸檔。
              <div className="mp2-actions">
                <Link to="/review" className="mp2-btn mp2-btn-primary">
                  查看方案
                </Link>
              </div>
            </div>
          ) : selected ? (
            <>
              <p className="mp2-kicker">{selected.kind}</p>
              <h2 className="mp2-page-title" style={{ fontSize: "1.2rem" }}>
                {selected.title}
              </h2>
              <p style={{ marginTop: 12, fontSize: "0.95rem", color: "var(--mp2-ink-secondary)" }}>
                {selected.excerpt}
              </p>
              {selected.symbol ? (
                <div className="mp2-actions">
                  <Link to={`/market/${selected.symbol}`} className="mp2-btn mp2-btn-primary">
                    開啟標的
                  </Link>
                  <Link to="/opportunities" className="mp2-btn">
                    決策工作區
                  </Link>
                </div>
              ) : null}
            </>
          ) : (
            <p className="muted">選擇左側項目開始閱讀</p>
          )}
        </article>

        {drawerOpen ? (
          <aside className="mp2-research-ctx" aria-label="上下文">
            <p className="mp2-kicker">上下文</p>
            <div className="mp2-evidence-row">
              <h3>Fear & Greed</h3>
              <p>{fear ? statusTag(fear.status) : "—"}</p>
            </div>
            <div className="mp2-evidence-row">
              <h3>Altcoin Season</h3>
              <p>{alt ? statusTag(alt.status) : "—"}</p>
            </div>
            <div className="mp2-evidence-row">
              <h3>Headlines</h3>
              <p>{news ? statusTag(news.status) : "—"}</p>
            </div>
            <div className="mp2-evidence-row">
              <h3>掃描新鮮度</h3>
              <p>{status?.freshness || "—"}</p>
            </div>
            <div className="mp2-evidence-row" style={{ borderBottom: 0 }}>
              <h3>合格候選</h3>
              <p className="mono">{status?.confirmedCandidates ?? "—"}</p>
            </div>
          </aside>
        ) : null}
      </div>
    </div>
  );
}
