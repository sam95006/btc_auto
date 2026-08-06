import { Link } from "react-router-dom";
import { useState } from "react";
import { useMarketScannerOverview } from "../../market/useMarketScanner";
import { OpportunityCard } from "../../components/OpportunityCard";
import { UiDensityToggle } from "../../member/UiDensityToggle";
import { loadUiDensity, saveUiDensity, type UiDensity } from "../../member/uiDensityPrefs";
import type { MarketCandidate } from "../../market/scannerApi";
import { displayOrPending, freshnessLabel } from "../../market/displayNull";
import { sideLabelZh, STAGE_LABEL_ZH, plainReason } from "../../market/scannerApi";

type ExpertTab =
  | "overview"
  | "evidence"
  | "structure"
  | "risk"
  | "history"
  | "quality";

const TAB_LABELS: Record<ExpertTab, string> = {
  overview: "Overview",
  evidence: "Evidence",
  structure: "Market Structure",
  risk: "Risk",
  history: "History",
  quality: "Data Quality",
};

function SimpleOpportunityCard({ candidate: c }: { candidate: MarketCandidate }) {
  const supporting = (c.reasons || []).slice(0, 3).map((r) => plainReason(r, true));
  const contradicting = (c.conflicts || []).slice(0, 2).map((r) => plainReason(r, true));
  const decision =
    c.side === "LONG" || c.side === "SHORT"
      ? sideLabelZh(c.side)
      : displayOrPending(null, "方向待確認");

  return (
    <article className="nx-opp-card nx-opp-v1821-simple" data-testid="opp-simple-card">
      <header className="nx-opp-card-head">
        <Link to={`/market/${c.symbol}`} className="nx-opp-sym mono">
          {c.symbol.replace("USDT", "")}
        </Link>
        <span className="muted">{decision}</span>
      </header>
      <dl className="nx-kv sm">
        <div>
          <dt>資料信任</dt>
          <dd>{displayOrPending(c.source, "UNAVAILABLE")}</dd>
        </div>
        <div>
          <dt>風險</dt>
          <dd>{c.riskScore != null ? String(c.riskScore) : "UNAVAILABLE"}</dd>
        </div>
        <div>
          <dt>更新</dt>
          <dd>{freshnessLabel(c.freshness)}</dd>
        </div>
      </dl>
      {supporting.length ? (
        <ul className="nx-opp-bullets">
          {supporting.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
      ) : null}
      {contradicting.length ? (
        <ul className="nx-opp-bullets conflict">
          {contradicting.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
      ) : null}
      <p className="muted sm">
        失效：{displayOrPending(c.invalidationContext, "尚未提供")}
      </p>
      <Link to={`/market/${c.symbol}`} className="nx-link" data-testid="opp-view-analysis">
        查看分析
      </Link>
    </article>
  );
}

function ExpertPanel({ c, tab }: { c: MarketCandidate; tab: ExpertTab }) {
  if (tab === "overview") {
    return <OpportunityCard candidate={c} simple={false} defaultExpanded />;
  }
  if (tab === "evidence") {
    return (
      <div className="nx-opp-expert-tab">
        <OpportunityCard candidate={c} simple={false} defaultExpanded />
      </div>
    );
  }
  if (tab === "structure") {
    return (
      <p className="muted">
        階段：{STAGE_LABEL_ZH[c.stage] || c.stage} · 結構欄位依 Symbol Workbench 綁定
      </p>
    );
  }
  if (tab === "risk") {
    return (
      <p className="muted">
        風險分數 {c.riskScore ?? "UNAVAILABLE"} · 不做 LONG/SHORT 偽造
      </p>
    );
  }
  if (tab === "history") {
    return <p className="muted">歷史軌跡請至標的工作台 History 分頁（深連結保留）。</p>;
  }
  return (
    <p className="muted">
      新鮮度 {freshnessLabel(c.freshness)} · 來源 {displayOrPending(c.source, "UNAVAILABLE")}
    </p>
  );
}

export function OpportunitiesPageV1821() {
  const { longs, shorts, loading, error } = useMarketScannerOverview();
  const [density, setDensity] = useState<UiDensity>(() => loadUiDensity());
  const [expertTab, setExpertTab] = useState<ExpertTab>("overview");
  const [focusId, setFocusId] = useState<string | null>(null);

  const all = [...longs, ...shorts];
  const focus = all.find((c) => c.id === focusId) ?? all[0] ?? null;

  const onDensity = (d: UiDensity) => {
    setDensity(d);
    saveUiDensity(d);
  };

  return (
    <div className="page-stack nx-opportunities-v1821" data-testid="opportunities-v1821">
      <header>
        <UiDensityToggle density={density} onDensityChange={onDensity} />
        <h1>機會</h1>
        <p className="muted">Scanner 候選 · 資料狀態誠實標示 · 非下單建議</p>
      </header>
      {loading ? <p className="muted">載入中…</p> : null}
      {error ? <div className="nx-banner-warn">掃描器暫不可用：{error}</div> : null}

      {density === "SIMPLE" ? (
        <div className="nx-opp-grid nx-opp-grid-p7">
          {all.length === 0 && !loading ? (
            <p className="muted" data-testid="no-eligible-opportunities">
              暫無合格機會 — eligible=0 或安全閘門生效中
            </p>
          ) : (
            all.slice(0, 24).map((c) => <SimpleOpportunityCard key={c.id} candidate={c} />)
          )}
        </div>
      ) : (
        <div className="nx-opp-expert-layout">
          <aside className="nx-opp-expert-list" aria-label="Opportunity list">
            {all.slice(0, 24).map((c) => (
              <button
                key={c.id}
                type="button"
                className={focus?.id === c.id ? "active" : undefined}
                onClick={() => setFocusId(c.id)}
              >
                {c.symbol.replace("USDT", "")} · {sideLabelZh(c.side)}
              </button>
            ))}
          </aside>
          <div className="nx-opp-expert-detail">
            <div className="nx-tab-row" role="tablist" aria-label="Expert opportunity tabs">
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
