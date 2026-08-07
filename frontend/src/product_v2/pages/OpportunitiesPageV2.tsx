import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { useMarketScannerOverview } from "../../market/useMarketScanner";
import type { MarketCandidate } from "../../market/scannerApi";
import { displayOrPending, freshnessLabel, fmtNum } from "../../market/displayNull";
import { sideLabelZh, STAGE_LABEL_ZH, plainReason } from "../../market/scannerApi";
import { partitionOpportunityCandidates } from "../../market/cryptoOpportunityFilter";
import { themeBadgeLabel } from "../../market/cryptoInstrumentPolicy";
import { formatUsd } from "../../market/freshness";
import { loadUiDensity } from "../../member/uiDensityPrefs";
import { WatchStarButton } from "../../components/WatchStarButton";
import { memberDataTrustLabel } from "../../market/marketMetricFunnel";
import { deriveRegime } from "../../market/marketSummary";

type DisclosureLevel = 1 | 2 | 3;

function unavailable(v: unknown): boolean {
  return v == null || v === "" || (typeof v === "number" && Number.isNaN(v));
}

function agoLabel(ts?: number | null) {
  if (!ts) return "—";
  const sec = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.round(sec / 60)}m`;
  return `${Math.round(sec / 3600)}h`;
}

function EvidencePanel({ c }: { c: MarketCandidate }) {
  const trust = memberDataTrustLabel({
    scannerFreshness: c.freshness,
    confirmedCandidates: c.stage === "CONFIRMED" ? 1 : 0,
  });
  const regime = deriveRegime({
    longCandidates: c.side === "LONG" ? 1 : 0,
    shortCandidates: c.side === "SHORT" ? 1 : 0,
    confirmedCandidates: c.stage === "CONFIRMED" ? 1 : 0,
    highRiskCandidates: (c.riskScore ?? 0) >= 70 ? 1 : 0,
    symbolCount: 1,
    freshness: c.freshness,
  });

  const rows: { label: string; value: string; muted?: boolean }[] = [
    {
      label: "Funding",
      value: c.fundingRate == null ? "尚無資料" : `${(c.fundingRate * 100).toFixed(4)}%`,
      muted: c.fundingRate == null,
    },
    {
      label: "OI 5m",
      value:
        c.oiChange5mPct == null
          ? "尚無資料"
          : `${c.oiChange5mPct > 0 ? "+" : ""}${c.oiChange5mPct.toFixed(2)}%`,
      muted: c.oiChange5mPct == null,
    },
    {
      label: "清算壓力（風險代理）",
      value: unavailable(c.riskScore) ? "尚無資料" : String(Math.round(c.riskScore as number)),
      muted: unavailable(c.riskScore),
    },
    {
      label: "流動性（價差 bps）",
      value: c.spreadBps == null ? "尚無資料" : c.spreadBps.toFixed(1),
      muted: c.spreadBps == null,
    },
    {
      label: "未平倉價值",
      value: c.openInterestValue == null ? "尚無資料" : String(c.openInterestValue),
      muted: c.openInterestValue == null,
    },
    {
      label: "Order Flow 代理",
      value: c.turnoverPace == null ? "尚無資料" : String(c.turnoverPace),
      muted: c.turnoverPace == null,
    },
    { label: "Regime", value: regime },
    {
      label: "資料品質",
      value: `${trust.label_zh} · ${freshnessLabel(c.freshness) || "未知"}`,
    },
    {
      label: "歷史／更新",
      value: `首次 ${agoLabel(c.firstSeenAt)} · 最近 ${agoLabel(c.lastUpdatedAt)}`,
    },
  ];

  return (
    <aside className="mp2-opp-evidence" aria-label="證據" data-testid="opp-context-drawer">
      <p className="mp2-kicker">證據</p>
      {rows.map((r) => (
        <div key={r.label} className="mp2-evidence-row">
          <h3>{r.label}</h3>
          <p className={r.muted ? "muted" : undefined}>{r.value}</p>
        </div>
      ))}
      <div className="mp2-evidence-row" style={{ borderBottom: 0 }}>
        <h3>最新變化</h3>
        <p>{plainReason(c.reasons?.[0] || "結構仍在觀察", true)}</p>
      </div>
    </aside>
  );
}

function DecisionCenter({
  c,
  level,
  onBack,
}: {
  c: MarketCandidate;
  level: DisclosureLevel;
  onBack?: () => void;
}) {
  const whyNow = plainReason(c.reasons?.[0] || "結構仍在觀察", level === 1);
  const supporting = (c.reasons || []).slice(0, 4).map((r) => plainReason(r, level === 1));
  const against = (c.conflicts || []).slice(0, 4).map((r) => plainReason(r, level === 1));
  const invalidation = displayOrPending(c.invalidationContext, "尚無明確失效條件");
  const riskText = unavailable(c.riskScore) ? "尚無資料" : fmtNum(c.riskScore);
  const theme = themeBadgeLabel(c.symbol, c.source, c.symbolType);
  const nowLine = `${sideLabelZh(c.side)} · ${STAGE_LABEL_ZH[c.stage] || c.stage} · ${
    freshnessLabel(c.freshness) || "更新未知"
  }${theme ? ` · ${theme}` : ""}`;

  return (
    <div className="mp2-opp-center" data-testid="opp-decision-workspace">
      {onBack ? (
        <button type="button" className="mp2-btn mp2-btn-ghost mobile-only" onClick={onBack}>
          ← 返回清單
        </button>
      ) : null}

      <header style={{ marginBottom: 8 }}>
        <Link to={`/market/${c.symbol}`} className="mono" style={{ fontSize: "1.35rem", fontWeight: 650, color: "var(--mp2-ink)" }}>
          {c.symbol.replace("USDT", "")}
        </Link>
        <p className="muted" style={{ margin: "4px 0 0", fontSize: "0.875rem" }}>
          {nowLine}
        </p>
      </header>

      <div className="mp2-decision-block">
        <h3>目前</h3>
        <p>{nowLine}</p>
      </div>
      <div className="mp2-decision-block">
        <h3>為什麼</h3>
        <p>{whyNow}</p>
      </div>
      <div className="mp2-decision-block">
        <h3>支持</h3>
        {supporting.length ? (
          <ul>
            {supporting.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">尚無支持證據</p>
        )}
      </div>
      <div className="mp2-decision-block against">
        <h3>反對</h3>
        {against.length ? (
          <ul>
            {against.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">目前未偵測到明顯反對證據</p>
        )}
      </div>
      <div className="mp2-decision-block">
        <h3>失效</h3>
        <p className={invalidation.includes("尚無") ? "muted" : undefined}>{invalidation}</p>
      </div>
      <div className="mp2-decision-block">
        <h3>風險</h3>
        <p className={unavailable(c.riskScore) ? "muted" : (c.riskScore as number) >= 70 ? "neg" : undefined}>
          {riskText}
          {!unavailable(c.riskScore) && (c.riskScore as number) >= 70 ? " · 偏高" : ""}
        </p>
      </div>

      <div className="mp2-actions">
        <Link to="/alerts" className="mp2-btn mp2-btn-primary">
          設警報
        </Link>
        <WatchStarButton symbol={c.symbol} />
        <Link to={`/market/${c.symbol}`} className="mp2-btn">
          深入分析
        </Link>
      </div>

      {level >= 2 ? (
        <div className="mp2-decision-block">
          <h3>交易者指標</h3>
          <dl className="mono" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: "0.875rem", margin: 0 }}>
            <div>
              <dt className="muted">機會分數</dt>
              <dd style={{ margin: 0 }}>{unavailable(c.opportunityScore) ? "尚無資料" : fmtNum(c.opportunityScore)}</dd>
            </div>
            <div>
              <dt className="muted">確認分數</dt>
              <dd style={{ margin: 0 }}>{unavailable(c.confirmationScore) ? "尚無資料" : fmtNum(c.confirmationScore)}</dd>
            </div>
            <div>
              <dt className="muted">價格</dt>
              <dd style={{ margin: 0 }}>{unavailable(c.currentPrice) ? "尚無資料" : formatUsd(c.currentPrice)}</dd>
            </div>
            <div>
              <dt className="muted">價 5m</dt>
              <dd style={{ margin: 0 }}>
                {c.priceChange5mPct == null
                  ? "尚無資料"
                  : `${c.priceChange5mPct > 0 ? "+" : ""}${c.priceChange5mPct.toFixed(2)}%`}
              </dd>
            </div>
          </dl>
        </div>
      ) : null}

      {level >= 3 ? (
        <div className="mp2-decision-block">
          <h3>研究細節</h3>
          <p className="muted" style={{ fontSize: "0.875rem" }}>
            來源 {displayOrPending(c.source, "尚無資料")} · 階段 {STAGE_LABEL_ZH[c.stage] || c.stage}
          </p>
        </div>
      ) : null}
    </div>
  );
}

/**
 * Product V2 Opportunities — true 3-region workspace.
 * LEFT navigator · CENTER decision · RIGHT collapsible evidence. NO card gallery.
 */
export function OpportunitiesPageV2() {
  const { longs, shorts, loading, error, status } = useMarketScannerOverview();
  const [focusId, setFocusId] = useState<string | null>(null);
  const defaultLevel: DisclosureLevel = loadUiDensity() === "EXPERT" ? 2 : 1;
  const [level, setLevel] = useState<DisclosureLevel>(defaultLevel);
  const [drawerOpen, setDrawerOpen] = useState(true);
  const [mobileDetail, setMobileDetail] = useState(false);

  const partitioned = partitionOpportunityCandidates([...longs, ...shorts]);
  const all = partitioned.crypto;
  const focus = all.find((c) => c.id === focusId) ?? all[0] ?? null;
  const eligibleZero =
    status?.confirmedCandidates === 0 ||
    (status?.confirmedCandidates == null && all.length === 0 && !loading);

  useEffect(() => {
    if (!focusId && all[0]) setFocusId(all[0].id);
  }, [all, focusId]);

  const selectRow = (id: string) => {
    setFocusId(id);
    setMobileDetail(true);
  };

  return (
    <div
      data-testid="product-v2-opportunities"
      data-nexus-product-generation="2"
      data-non-crypto-in-crypto-opportunity-count={partitioned.non_crypto_symbol_in_crypto_opportunity_count}
    >
      <header style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-start" }}>
        <div style={{ flex: 1, minWidth: 200 }}>
          <h1 className="mp2-page-title">機會</h1>
          <p className="mp2-page-sub">三區決策工作區 · 非下單建議</p>
        </div>
        <button
          type="button"
          className="mp2-btn desktop-only"
          onClick={() => setDrawerOpen((v) => !v)}
          aria-pressed={drawerOpen}
        >
          {drawerOpen ? "收合證據" : "展開證據"}
        </button>
        <div className="mp2-level" role="group" aria-label="資訊層級">
          <button type="button" className={level === 1 ? "active" : undefined} onClick={() => setLevel(1)}>
            L1
          </button>
          <button type="button" className={level === 2 ? "active" : undefined} onClick={() => setLevel(2)}>
            L2
          </button>
          <button type="button" className={level === 3 ? "active" : undefined} onClick={() => setLevel(3)}>
            L3
          </button>
        </div>
      </header>

      {error ? <div className="mp2-banner">{error}</div> : null}
      {eligibleZero ? (
        <div className="mp2-empty" data-testid="no-eligible-opportunities">
          目前沒有通過安全條件的機會；左側仍顯示觀察候選。
        </div>
      ) : null}

      <div
        className={`mp2-opp${drawerOpen ? "" : " no-evidence"}${mobileDetail ? " mobile-detail" : " mobile-list"}`}
      >
        <nav className="mp2-opp-nav" aria-label="機會導覽">
          <p className="mp2-kicker">候選 {all.length}</p>
          {loading && !all.length ? <p className="muted">載入中…</p> : null}
          {!loading && !all.length ? <p className="muted">暫無候選</p> : null}
          {all.map((c) => (
            <button
              key={c.id}
              type="button"
              className={`mp2-opp-nav-item${focus?.id === c.id ? " is-active" : ""}`}
              onClick={() => selectRow(c.id)}
            >
              <span className="sym">{c.symbol.replace("USDT", "")}</span>
              <span className="meta">
                {sideLabelZh(c.side)} · {STAGE_LABEL_ZH[c.stage] || c.stage} · 機會{" "}
                {c.opportunityScore == null ? "—" : Math.round(c.opportunityScore)}
              </span>
            </button>
          ))}
          {partitioned.crossAsset.length ? (
            <p className="muted" style={{ fontSize: "0.75rem", marginTop: 10 }}>
              跨資產 {partitioned.crossAsset.length}（另區）
            </p>
          ) : null}
        </nav>

        {focus ? (
          <DecisionCenter c={focus} level={level} onBack={() => setMobileDetail(false)} />
        ) : (
          <div className="mp2-opp-center">
            <p className="muted">選擇左側候選以檢視決策</p>
          </div>
        )}

        {drawerOpen && focus ? <EvidencePanel c={focus} /> : null}
      </div>
    </div>
  );
}
