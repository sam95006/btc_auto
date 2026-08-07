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
import { useLiveMarketRanking } from "../useLiveMarketRanking";
import { formatRankMove } from "../../market/liveMarketRanking";
import { deriveRegime } from "../../market/marketSummary";
import { computeAvgFunding } from "../../market/marketAvgFunding";

type Cat = "market" | "derivatives" | "macro" | "news" | "historical";

type FeedItem = {
  id: string;
  title: string;
  excerpt: string;
  body: string;
  kind: Cat;
  ts: number;
  symbol?: string;
  locked?: boolean;
  source?: string;
};

function agoLabel(ts?: number | null) {
  if (!ts) return "—";
  const sec = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.round(sec / 60)}m`;
  return `${Math.round(sec / 3600)}h`;
}

function valueFromMetric(m: ParityMetric<unknown> | null): string {
  if (!m) return "尚無資料";
  const v = m.value as Record<string, unknown> | number | string | null | undefined;
  if (v == null) return statusTag(m.status);
  if (typeof v === "number" || typeof v === "string") return String(v);
  if (typeof v === "object") {
    const obj = v as Record<string, unknown>;
    if (obj.value != null) return String(obj.value);
    if (obj.index != null) return String(obj.index);
    if (obj.score != null) return String(obj.score);
    if (Array.isArray(obj.headlines) && obj.headlines.length) {
      return String((obj.headlines[0] as { title?: string })?.title || obj.headlines[0]);
    }
  }
  return statusTag(m.status);
}

/** Product V2 Research Terminal — real values when available, no fake articles. */
export function ResearchPageV2() {
  const [news, setNews] = useState<ParityMetric<unknown> | null>(null);
  const [fear, setFear] = useState<ParityMetric<unknown> | null>(null);
  const [alt, setAlt] = useState<ParityMetric<unknown> | null>(null);
  const { status, longs, shorts, events, loading } = useMarketScannerOverview();
  const anomalies = useMarketAnomalies();
  const ranking = useLiveMarketRanking();
  const [cat, setCat] = useState<Cat>("market");
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
  const regime = deriveRegime({
    longCandidates: status?.longCandidates,
    shortCandidates: status?.shortCandidates,
    confirmedCandidates: status?.confirmedCandidates,
    highRiskCandidates: status?.highRiskCandidates,
    breadth: status?.breadth,
    symbolCount: status?.symbolCount,
    freshness: status?.freshness,
  });
  const funding = computeAvgFunding([...longs, ...shorts], status?.freshness);

  const feed: FeedItem[] = useMemo(() => {
    const items: FeedItem[] = [];

    items.push({
      id: "market-regime",
      title: `市場狀態 · ${regime}`,
      excerpt: `廣度 升 ${status?.breadth?.rising ?? "—"}／降 ${status?.breadth?.falling ?? "—"} · 合格 ${status?.confirmedCandidates ?? 0}`,
      body: `Regime ${regime}。掃描宇宙 ${status?.symbolCount ?? "—"} · Live Radar 活躍 ${ranking.active_count} · 合格 ${ranking.qualified_count}。資料 ${status?.freshness || "—"}。`,
      kind: "market",
      ts: status?.generatedAt || Date.now(),
      source: status?.source || "scanner",
    });

    for (const r of ranking.rows.slice(0, 8)) {
      items.push({
        id: `rank-${r.candidate_id}`,
        title: `#${r.rank} ${r.symbol.replace("USDT", "")} · ${formatRankMove(r)}`,
        excerpt: `${STAGE_LABEL_ZH[r.stage] || r.stage} · score ${Math.round(r.rank_score)} · ${r.primary_reason}`,
        body: `排名分數 ${r.rank_score}（${r.rank_score_version}）。機會 ${Math.round(r.rank_score_components.opportunity)}／確認 ${Math.round(r.rank_score_components.confirmation)}／風險 ${Math.round(r.rank_score_components.risk)}。Activity ${r.activity_state} · OI ${r.oi_change ?? "—"} · Funding ${r.funding_rate ?? "—"}。`,
        kind: "market",
        ts: r.last_rank_update,
        symbol: r.symbol,
        source: "live_radar",
      });
    }

    items.push({
      id: "deriv-funding",
      title: "衍生品 · 平均 Funding",
      excerpt:
        funding.status === "live" && funding.value
          ? funding.value.display
          : funding.status === "pending"
            ? "樣本不足"
            : "尚無資料",
      body: `Funding 狀態 ${funding.status}。數值僅來自公開掃描候選；缺資料時顯示尚無，不捏造。`,
      kind: "derivatives",
      ts: status?.generatedAt || Date.now(),
      source: "scanner_candidates",
    });

    for (const a of anomalies.slice(0, 8)) {
      items.push({
        id: `anom-${a.id}`,
        title: a.title || a.type,
        excerpt: a.explanation || "市場異動",
        body: a.explanation || "異動事件來自市場異常層，非編造文章。",
        kind: "derivatives",
        ts: a.lastSeenAt || a.observedAt || 0,
        symbol: a.symbol,
        source: "anomaly",
      });
    }

    items.push({
      id: "macro-fear",
      title: "Macro · Fear & Greed",
      excerpt: valueFromMetric(fear),
      body: `Fear & Greed：${valueFromMetric(fear)}（狀態 ${fear ? statusTag(fear.status) : "—"}）。`,
      kind: "macro",
      ts: Date.now(),
      source: "fear_greed_provider",
    });
    items.push({
      id: "macro-alt",
      title: "Macro · Altcoin Season",
      excerpt: valueFromMetric(alt),
      body: `Altcoin Season：${valueFromMetric(alt)}（狀態 ${alt ? statusTag(alt.status) : "—"}）。`,
      kind: "macro",
      ts: Date.now(),
      source: "altcoin_season_provider",
    });

    const headlines = (news?.value as { headlines?: { title?: string; url?: string }[] } | undefined)
      ?.headlines;
    if (Array.isArray(headlines) && headlines.length) {
      headlines.slice(0, 5).forEach((h, i) => {
        items.push({
          id: `news-${i}`,
          title: h.title || `Headline ${i + 1}`,
          excerpt: "公開新聞來源",
          body: h.title || "—",
          kind: "news",
          ts: Date.now() - i * 1000,
          source: "news_provider",
        });
      });
    } else {
      items.push({
        id: "news-empty",
        title: "News",
        excerpt: news ? statusTag(news.status) : "尚無資料",
        body: "目前沒有可用的公開新聞標題；不顯示假文章。",
        kind: "news",
        ts: Date.now(),
        source: "news_provider",
      });
    }

    for (const e of events.slice(0, 6)) {
      items.push({
        id: `hist-${e.id}`,
        title: `${e.symbol.replace("USDT", "")} · ${e.type || "事件"}`,
        excerpt: e.explanation || "掃描事件",
        body: e.explanation || "—",
        kind: "historical",
        ts: e.timestamp || 0,
        symbol: e.symbol,
        source: "scanner_events",
        locked: historyLocked && e.timestamp < Date.now() - 86400000 * 3,
      });
    }

    for (const c of crypto.slice(0, 4)) {
      items.push({
        id: `cand-${c.id}`,
        title: `${c.symbol.replace("USDT", "")} · ${STAGE_LABEL_ZH[c.stage] || c.stage}`,
        excerpt: plainReason(c.reasons?.[0] || "結構觀察", true),
        body: plainReason(c.reasons?.join("；") || "結構觀察", false),
        kind: "historical",
        ts: c.lastUpdatedAt || 0,
        symbol: c.symbol,
        source: "candidates",
      });
    }

    if (historyLocked) {
      items.push({
        id: "history-lock",
        title: "研究歷史（進階）",
        excerpt: "升級後可回看完整研究軌跡",
        body: "歷史歸檔為進階能力。",
        kind: "historical",
        ts: 0,
        locked: true,
      });
    }

    return items.sort((a, b) => b.ts - a.ts);
  }, [
    alt,
    anomalies,
    crypto,
    events,
    fear,
    funding,
    historyLocked,
    news,
    ranking.active_count,
    ranking.qualified_count,
    ranking.rows,
    regime,
    status,
  ]);

  const filtered = feed.filter((f) => f.kind === cat);

  useEffect(() => {
    if (!selectedId && filtered[0]) setSelectedId(filtered[0].id);
  }, [filtered, selectedId]);

  const selected = filtered.find((f) => f.id === selectedId) ?? filtered[0] ?? null;

  const cats: { id: Cat; label: string }[] = [
    { id: "market", label: "Market" },
    { id: "derivatives", label: "Derivatives" },
    { id: "macro", label: "Macro" },
    { id: "news", label: "News" },
    { id: "historical", label: "Historical" },
  ];

  return (
    <div data-testid="product-v2-research" data-nexus-product-generation="2">
      <header style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-start" }}>
        <div style={{ flex: 1 }}>
          <h1 className="mp2-page-title">研究</h1>
          <p className="mp2-page-sub">研究終端 · 真實數值優先</p>
        </div>
        <button type="button" className="mp2-btn desktop-only" onClick={() => setDrawerOpen((v) => !v)}>
          {drawerOpen ? "收合上下文" : "展開上下文"}
        </button>
      </header>

      <div className="mp2-chip-row" style={{ marginTop: 10 }} role="tablist" aria-label="研究分類">
        {cats.map((c) => (
          <button
            key={c.id}
            type="button"
            className={cat === c.id ? "active" : undefined}
            onClick={() => {
              setCat(c.id);
              setSelectedId(null);
            }}
          >
            {c.label}
          </button>
        ))}
      </div>

      <div className="mp2-research">
        <div className="mp2-research-feed" aria-label="研究資訊流">
          <p className="mp2-kicker">資訊流</p>
          {loading && !filtered.length ? <p className="muted">載入中…</p> : null}
          {filtered.map((item) => (
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
                {selected.body}
              </p>
              <p className="muted" style={{ fontSize: "0.75rem", marginTop: 12 }}>
                來源 {selected.source || "—"} · {agoLabel(selected.ts)}
              </p>
              {selected.symbol ? (
                <div className="mp2-actions">
                  <Link to={`/market/${selected.symbol}`} className="mp2-btn mp2-btn-primary">
                    市場終端
                  </Link>
                  <Link to="/opportunities" className="mp2-btn">
                    探索
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
              <p>{valueFromMetric(fear)}</p>
            </div>
            <div className="mp2-evidence-row">
              <h3>Altcoin Season</h3>
              <p>{valueFromMetric(alt)}</p>
            </div>
            <div className="mp2-evidence-row">
              <h3>Radar 活躍</h3>
              <p className="mono">{ranking.active_count}</p>
            </div>
            <div className="mp2-evidence-row">
              <h3>合格</h3>
              <p className="mono">{status?.confirmedCandidates ?? ranking.qualified_count}</p>
            </div>
            <div className="mp2-evidence-row" style={{ borderBottom: 0 }}>
              <h3>掃描新鮮度</h3>
              <p>{status?.freshness || "—"}</p>
            </div>
          </aside>
        ) : null}
      </div>
    </div>
  );
}
