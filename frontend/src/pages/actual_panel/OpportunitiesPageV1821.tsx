import { Link } from "react-router-dom";
import { useState } from "react";
import { useMarketScannerOverview } from "../../market/useMarketScanner";
import { OpportunityCard } from "../../components/OpportunityCard";
import { UiDensityToggle } from "../../member/UiDensityToggle";
import { loadUiDensity, saveUiDensity, type UiDensity } from "../../member/uiDensityPrefs";
import type { MarketCandidate } from "../../market/scannerApi";
import { displayOrPending, freshnessLabel } from "../../market/displayNull";
import { sideLabelZh, STAGE_LABEL_ZH } from "../../market/scannerApi";
import { partitionOpportunityCandidates } from "../../market/cryptoOpportunityFilter";
import { themeBadgeLabel } from "../../market/cryptoInstrumentPolicy";

type ExpertTab =
  | "overview"
  | "evidence"
  | "structure"
  | "risk"
  | "history"
  | "quality";

const TAB_LABELS: Record<ExpertTab, string> = {
  overview: "總覽",
  evidence: "證據",
  structure: "結構",
  risk: "風險",
  history: "歷史",
  quality: "資料品質",
};

function ExpertPanel({ c, tab }: { c: MarketCandidate; tab: ExpertTab }) {
  if (tab === "overview" || tab === "evidence") {
    return <OpportunityCard candidate={c} simple={false} defaultExpanded />;
  }
  if (tab === "structure") {
    return (
      <p className="muted">
        階段：{STAGE_LABEL_ZH[c.stage] || c.stage} · 結構欄位依標的工作台綁定
      </p>
    );
  }
  if (tab === "risk") {
    return (
      <p className="muted">
        風險分數 {c.riskScore != null ? c.riskScore : "UNAVAILABLE"} · 不做 LONG/SHORT 偽造
      </p>
    );
  }
  if (tab === "history") {
    return <p className="muted">歷史軌跡請至標的工作台 History 分頁。</p>;
  }
  return (
    <p className="muted">
      新鮮度 {freshnessLabel(c.freshness) || "UNAVAILABLE"} · 來源{" "}
      {displayOrPending(c.source, "UNAVAILABLE")}
    </p>
  );
}

export function OpportunitiesPageV1821() {
  const { longs, shorts, loading, error, status } = useMarketScannerOverview();
  const [density, setDensity] = useState<UiDensity>(() => loadUiDensity());
  const [expertTab, setExpertTab] = useState<ExpertTab>("overview");
  const [focusId, setFocusId] = useState<string | null>(null);

  const partitioned = partitionOpportunityCandidates([...longs, ...shorts]);
  const all = partitioned.crypto;
  const crossAsset = partitioned.crossAsset;
  const focus = all.find((c) => c.id === focusId) ?? all[0] ?? null;
  const eligibleZero =
    status?.confirmedCandidates === 0 ||
    (status?.confirmedCandidates == null && all.length === 0 && !loading);

  const onDensity = (d: UiDensity) => {
    setDensity(d);
    saveUiDensity(d);
  };

  return (
    <div
      className="page-stack nx-opportunities-v1821"
      data-testid="opportunities-v1821"
      data-non-crypto-in-crypto-opportunity-count={partitioned.non_crypto_symbol_in_crypto_opportunity_count}
    >
      <header className="nx-ov-global-header">
        <div>
          <h1>機會</h1>
          <p className="muted" style={{ margin: "4px 0 0" }}>
            掃描候選 · 資料狀態誠實標示 · 非下單建議
          </p>
        </div>
        <UiDensityToggle density={density} onDensityChange={onDensity} />
      </header>
      {loading ? <p className="muted">載入中…</p> : null}
      {error ? <div className="nx-banner-warn">掃描器暫不可用：{error}</div> : null}

      {eligibleZero && !loading ? (
        <div className="nx-eligible-state is-zero" data-testid="no-eligible-opportunities">
          <p className="nx-eligible-headline">目前沒有符合安全條件的市場機會</p>
          <p className="nx-watch-note">
            下列清單若出現，僅為觀察候選或歷史殘留，不代表合格可交易機會；不暗示做多／做空可執行。
          </p>
        </div>
      ) : null}

      {crossAsset.length ? (
        <div className="nx-banner-warn" data-testid="cross-asset-context-only">
          跨資產標的（{crossAsset.map((c) => c.symbol.replace("USDT", "")).join(", ")}）·
          CROSS_ASSET_CONTEXT_ONLY · 已自加密 Opportunities 排名移除
        </div>
      ) : null}

      {density === "SIMPLE" ? (
        <div className="nx-opp-grid nx-opp-grid-p7">
          {all.length === 0 && !loading ? (
            <p className="muted">暫無可展示候選</p>
          ) : (
            all.slice(0, 24).map((c) => (
              <div key={c.id} data-tradable={eligibleZero ? "false" : "observe"}>
                <OpportunityCard candidate={c} simple />
                {eligibleZero ? (
                  <p className="muted sm">尚未通過安全條件 · 不可視為交易建議</p>
                ) : null}
                {themeBadgeLabel(c.symbol, c.source, c.symbolType) ? (
                  <p className="muted sm">{themeBadgeLabel(c.symbol, c.source, c.symbolType)}</p>
                ) : null}
              </div>
            ))
          )}
        </div>
      ) : (
        <div className="nx-opp-expert-layout">
          <aside className="nx-opp-expert-list" aria-label="Opportunity list">
            {all.length === 0 && !loading ? (
              <p className="muted">尚無候選</p>
            ) : (
              all.slice(0, 24).map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className={focus?.id === c.id ? "active" : undefined}
                  onClick={() => setFocusId(c.id)}
                >
                  {c.symbol.replace("USDT", "")} · {sideLabelZh(c.side)}
                </button>
              ))
            )}
          </aside>
          <div className="nx-opp-expert-detail">
            <div className="nx-tab-row" role="tablist" aria-label="專業機會分頁">
              {(Object.keys(TAB_LABELS) as ExpertTab[]).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  role="tab"
                  aria-selected={expertTab === tab}
                  className={expertTab === tab ? "active" : undefined}
                  onClick={() => setExpertTab(tab)}
                >
                  {TAB_LABELS[tab]}
                </button>
              ))}
            </div>
            {focus ? (
              <ExpertPanel c={focus} tab={expertTab} />
            ) : (
              <p className="muted">尚無候選可展示</p>
            )}
          </div>
        </div>
      )}

      <p className="muted sm">
        <Link to="/overview">返回總覽</Link>
      </p>
    </div>
  );
}
