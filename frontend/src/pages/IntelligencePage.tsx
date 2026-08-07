import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { newsProvider } from "../market/providers/newsProvider";
import { fearGreedProvider } from "../market/providers/fearGreedProvider";
import { altcoinSeasonProvider } from "../market/providers/altcoinSeasonProvider";
import { statusTag, type ParityMetric } from "../market/parityContracts";
import { useMarketScannerOverview } from "../market/useMarketScanner";
import { useMarketAnomalies } from "../market/useMarketAnomalies";
import { STAGE_LABEL_ZH, plainReason } from "../market/scannerApi";
import { partitionOpportunityCandidates } from "../market/cryptoOpportunityFilter";

type FeedItem = {
  id: string;
  title: string;
  excerpt: string;
  kind: "event" | "anomaly" | "candidate" | "layer";
  ts: number;
  symbol?: string;
};

/**
 * V18.2.9 UX — Intelligence as reading / investigation workspace.
 * Left feed · main article/evidence · right context drawer.
 * Not equal square cards.
 */
export function IntelligencePage() {
  const [news, setNews] = useState<ParityMetric<unknown> | null>(null);
  const [fear, setFear] = useState<ParityMetric<unknown> | null>(null);
  const [alt, setAlt] = useState<ParityMetric<unknown> | null>(null);
  const { status, longs, shorts, events, loading } = useMarketScannerOverview();
  const anomalies = useMarketAnomalies();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(true);

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
        excerpt: e.explanation,
        kind: "event",
        ts: e.timestamp || 0,
        symbol: e.symbol,
      });
    }

    for (const c of crypto.slice(0, 8)) {
      items.push({
        id: `cand-${c.id}`,
        title: `${c.symbol.replace("USDT", "")} · ${STAGE_LABEL_ZH[c.stage] || c.stage}`,
        excerpt: plainReason(c.reasons?.[0] || "結構仍在觀察", true),
        kind: "candidate",
        ts: c.lastUpdatedAt || 0,
        symbol: c.symbol,
      });
    }

    items.sort((a, b) => b.ts - a.ts);
    return items;
  }, [anomalies, events, crypto, status?.generatedAt]);

  useEffect(() => {
    if (!selectedId && feed[0]) setSelectedId(feed[0].id);
  }, [feed, selectedId]);

  const selected = feed.find((f) => f.id === selectedId) ?? feed[0] ?? null;
  const selectedCand = selected?.symbol
    ? crypto.find((c) => c.symbol === selected.symbol)
    : null;
  const selectedAnom = selected?.id.startsWith("anom-")
    ? anomalies.find((a) => `anom-${a.id}` === selected.id)
    : null;

  const layers = [
    { name: "公開市場掃描", status: "live" as const, note: "價格／OI／Funding" },
    { name: "市場異動雷達", status: "live" as const, note: "異常與證據欄位" },
    {
      name: "News",
      status: "pending" as const,
      note: news?.coverageNote || "供應商尚未就緒",
      tag: news ? statusTag(news.status) : undefined,
    },
    {
      name: "Fear & Greed",
      status: "pending" as const,
      note: fear?.coverageNote || "供應商尚未就緒",
      tag: fear ? statusTag(fear.status) : undefined,
    },
    {
      name: "Altcoin Season",
      status: "pending" as const,
      note: alt?.coverageNote || "供應商尚未就緒",
      tag: alt ? statusTag(alt.status) : undefined,
    },
    { name: "Macro", status: "pending" as const, note: "供應商尚未就緒" },
    { name: "On-chain", status: "pending" as const, note: "供應商尚未就緒" },
  ];

  const related = crypto
    .filter((c) => c.symbol !== selected?.symbol)
    .slice(0, 5)
    .map((c) => ({
      symbol: c.symbol.replace("USDT", ""),
      href: `/market/${c.symbol}`,
      stage: STAGE_LABEL_ZH[c.stage] || c.stage,
    }));

  return (
    <div className="v1829-research" data-testid="research-v1829" data-product-gen="v18_2_9_ux">
      <header className="v1829-research-head">
        <div>
          <h1 className="v1829-page-title">研究</h1>
          <p className="v1829-page-sub" style={{ marginBottom: 0 }}>
            閱讀／調查工作區 · 左側情報流 · 主文證據 · 右側上下文 · pending 不捏造
          </p>
        </div>
        <button
          type="button"
          className="v1829-btn v1829-btn-tertiary desktop-only"
          onClick={() => setDrawerOpen((v) => !v)}
        >
          {drawerOpen ? "收合上下文" : "展開上下文"}
        </button>
      </header>

      <div className={`v1829-research-workspace${drawerOpen ? "" : " drawer-closed"}`}>
        <aside className="v1829-research-feed" aria-label="情報流">
          {loading && feed.length === 0 ? (
            <p className="muted">載入中…</p>
          ) : feed.length === 0 ? (
            <p className="muted">目前無情報項目</p>
          ) : (
            feed.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`v1829-feed-item${selected?.id === item.id ? " is-active" : ""}`}
                onClick={() => setSelectedId(item.id)}
              >
                <span className="kind">{item.kind === "layer" ? "層" : item.kind === "anomaly" ? "異動" : item.kind === "event" ? "事件" : "候選"}</span>
                <span className="title">{item.title}</span>
                <span className="excerpt muted">{item.excerpt}</span>
              </button>
            ))
          )}
        </aside>

        <article className="v1829-research-article" aria-label="主文與證據">
          {!selected ? (
            <p className="muted">選擇左側項目開始閱讀</p>
          ) : (
            <>
              <p className="v1829-kicker">
                {selected.kind === "layer"
                  ? "情報層"
                  : selected.kind === "anomaly"
                    ? "異動調查"
                    : selected.kind === "event"
                      ? "事件記錄"
                      : "候選閱讀"}
              </p>
              <h2 className="v1829-article-title">{selected.title}</h2>
              <p className="v1829-article-lede">{selected.excerpt}</p>

              {selected.kind === "layer" ? (
                <div className="v1829-article-body">
                  <h3>情報層狀態</h3>
                  <ul className="v1829-layer-list">
                    {layers.map((p) => (
                      <li key={p.name}>
                        <strong>{p.name}</strong>
                        <span className={p.status === "live" ? "side-long" : "muted"}>
                          {p.status === "live" ? "即時" : p.tag || "尚未就緒"}
                        </span>
                        <span className="muted">{p.note}</span>
                      </li>
                    ))}
                  </ul>
                  <p className="muted" style={{ fontSize: "0.8125rem" }}>
                    監控 {status?.symbolCount ?? "—"} · 合格 {status?.confirmedCandidates ?? "—"}
                  </p>
                </div>
              ) : null}

              {selectedCand ? (
                <div className="v1829-article-body">
                  <h3>證據摘錄</h3>
                  <ul>
                    {(selectedCand.reasons || []).slice(0, 5).map((r) => (
                      <li key={r}>{plainReason(r, false)}</li>
                    ))}
                  </ul>
                  {(selectedCand.conflicts || []).length ? (
                    <>
                      <h3>反對證據</h3>
                      <ul className="against">
                        {selectedCand.conflicts.slice(0, 4).map((r) => (
                          <li key={r}>{plainReason(r, false)}</li>
                        ))}
                      </ul>
                    </>
                  ) : null}
                  <div className="v1829-action-strip">
                    <Link to={`/market/${selectedCand.symbol}`} className="v1829-btn v1829-btn-primary">
                      深入分析
                    </Link>
                    <Link to="/opportunities" className="v1829-btn v1829-btn-secondary">
                      決策工作區
                    </Link>
                  </div>
                </div>
              ) : null}

              {selectedAnom ? (
                <div className="v1829-article-body">
                  <h3>異動細節</h3>
                  <p>{selectedAnom.explanation || "尚無進一步說明"}</p>
                  {selectedAnom.symbol ? (
                    <Link
                      to={`/market/${selectedAnom.symbol}`}
                      className="v1829-btn v1829-btn-secondary"
                      style={{ marginTop: 12 }}
                    >
                      開啟標的 →
                    </Link>
                  ) : null}
                </div>
              ) : null}

              {selected.kind === "event" && selected.symbol ? (
                <div className="v1829-action-strip">
                  <Link to={`/market/${selected.symbol}`} className="v1829-btn v1829-btn-secondary">
                    開啟標的 →
                  </Link>
                </div>
              ) : null}
            </>
          )}
        </article>

        {drawerOpen ? (
          <aside className="v1829-research-drawer" aria-label="研究上下文">
            <div className="drawer-block">
              <h3>來源</h3>
              <p style={{ margin: 0, fontSize: "0.875rem" }}>
                {selected?.kind === "layer"
                  ? "掃描器公開層"
                  : selected?.kind === "anomaly"
                    ? "異動雷達"
                    : selected?.kind === "event"
                      ? "掃描事件"
                      : "候選引擎"}
              </p>
            </div>
            <div className="drawer-block">
              <h3>資料品質</h3>
              <p style={{ margin: 0, fontSize: "0.875rem" }}>
                {status?.freshness ? `掃描 ${status.freshness}` : "更新狀態未知"}
              </p>
            </div>
            <div className="drawer-block">
              <h3>類比／相關</h3>
              {related.length === 0 ? (
                <p className="muted" style={{ margin: 0, fontSize: "0.875rem" }}>
                  尚無相關候選
                </p>
              ) : (
                <ul className="v1829-related-list">
                  {related.map((r) => (
                    <li key={r.symbol}>
                      <Link to={r.href} className="mono">
                        {r.symbol}
                      </Link>
                      <span className="muted">{r.stage}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="drawer-block" style={{ borderBottom: 0 }}>
              <h3>時間軸</h3>
              <ul className="v1829-timeline">
                {feed.slice(0, 6).map((t) => (
                  <li key={`tl-${t.id}`}>
                    <span className="dot" aria-hidden />
                    <div>
                      <button
                        type="button"
                        className="v1829-timeline-link"
                        onClick={() => setSelectedId(t.id)}
                      >
                        {t.title}
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </aside>
        ) : null}
      </div>
    </div>
  );
}
