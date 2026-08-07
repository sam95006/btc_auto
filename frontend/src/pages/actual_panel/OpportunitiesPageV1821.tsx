import { Link } from "react-router-dom";
import { useState } from "react";
import { useMarketScannerOverview } from "../../market/useMarketScanner";
import type { MarketCandidate } from "../../market/scannerApi";
import { displayOrPending, freshnessLabel, fmtNum } from "../../market/displayNull";
import { sideLabelZh, STAGE_LABEL_ZH, plainReason } from "../../market/scannerApi";
import { partitionOpportunityCandidates } from "../../market/cryptoOpportunityFilter";
import { themeBadgeLabel } from "../../market/cryptoInstrumentPolicy";
import { formatUsd } from "../../market/freshness";
import { loadUiDensity } from "../../member/uiDensityPrefs";

type DisclosureLevel = 1 | 2 | 3;

function unavailable(v: unknown): boolean {
  return v == null || v === "" || (typeof v === "number" && Number.isNaN(v));
}

function DecisionWorkspace({ c, level }: { c: MarketCandidate; level: DisclosureLevel }) {
  const whyNow = plainReason(c.reasons?.[0] || "結構仍在觀察", level === 1);
  const supporting = (c.reasons || []).slice(0, 4).map((r) => plainReason(r, level === 1));
  const against = (c.conflicts || []).slice(0, 4).map((r) => plainReason(r, level === 1));
  const invalidation = displayOrPending(c.invalidationContext, "UNAVAILABLE");
  const riskText = unavailable(c.riskScore) ? "UNAVAILABLE" : fmtNum(c.riskScore);
  const theme = themeBadgeLabel(c.symbol, c.source, c.symbolType);

  return (
    <div className="v1828-opp-detail" data-testid="opp-decision-workspace">
      <header style={{ marginBottom: 16 }}>
        <Link to={`/market/${c.symbol}`} className="mono" style={{ fontSize: "1.25rem", fontWeight: 650 }}>
          {c.symbol.replace("USDT", "")}
        </Link>
        <p className="muted sm" style={{ margin: "4px 0 0" }}>
          <span className={c.side === "LONG" ? "side-long" : c.side === "SHORT" ? "side-short" : ""}>
            {sideLabelZh(c.side)}
          </span>
          {" · "}
          {STAGE_LABEL_ZH[c.stage] || c.stage}
          {" · "}
          {freshnessLabel(c.freshness) || "UNAVAILABLE"}
          {theme ? ` · ${theme}` : ""}
        </p>
      </header>

      {/* Decision first: Why / Support / Against / Invalidation */}
      <div className="v1828-decision-block">
        <h3>為何現在？</h3>
        <p>{whyNow}</p>
      </div>

      <div className="v1828-decision-block">
        <h3>支持</h3>
        {supporting.length ? (
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {supporting.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">UNAVAILABLE</p>
        )}
      </div>

      <div className="v1828-decision-block against">
        <h3>反對</h3>
        {against.length ? (
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {against.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">目前未偵測到明顯反方證據</p>
        )}
      </div>

      <div className="v1828-decision-block">
        <h3>失效條件</h3>
        <p className={invalidation === "UNAVAILABLE" ? "muted" : undefined}>{invalidation}</p>
      </div>

      <div className="v1828-decision-block">
        <h3>風險</h3>
        <p className={unavailable(c.riskScore) ? "muted" : (c.riskScore as number) >= 70 ? "side-short" : undefined}>
          {riskText}
          {!unavailable(c.riskScore) && (c.riskScore as number) >= 70 ? " · 偏高" : ""}
        </p>
      </div>

      {/* Level 2+ trader metrics */}
      {level >= 2 ? (
        <div className="v1828-decision-block">
          <h3>交易者指標</h3>
          <dl className="nx-kv mono sm" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <div>
              <dt className="muted">機會分數</dt>
              <dd>{unavailable(c.opportunityScore) ? "UNAVAILABLE" : fmtNum(c.opportunityScore)}</dd>
            </div>
            <div>
              <dt className="muted">確認分數</dt>
              <dd>{unavailable(c.confirmationScore) ? "UNAVAILABLE" : fmtNum(c.confirmationScore)}</dd>
            </div>
            <div>
              <dt className="muted">價格</dt>
              <dd>{unavailable(c.currentPrice) ? "UNAVAILABLE" : formatUsd(c.currentPrice)}</dd>
            </div>
            <div>
              <dt className="muted">價 5m</dt>
              <dd>
                {c.priceChange5mPct == null
                  ? "UNAVAILABLE"
                  : `${c.priceChange5mPct > 0 ? "+" : ""}${c.priceChange5mPct.toFixed(2)}%`}
              </dd>
            </div>
          </dl>
        </div>
      ) : null}

      {/* Level 3 research + below-fold Funding/OI */}
      {level >= 3 ? (
        <div className="v1828-decision-block">
          <h3>研究細節</h3>
          <p className="muted sm">
            來源 {displayOrPending(c.source, "UNAVAILABLE")} · 階段{" "}
            {STAGE_LABEL_ZH[c.stage] || c.stage}
          </p>
          {c.scoreBreakdown ? (
            <p className="muted sm">分數拆解已綁定 · 詳見標的工作台</p>
          ) : (
            <p className="muted sm">分數拆解 UNAVAILABLE</p>
          )}
        </div>
      ) : null}

      <details className="v1828-below-fold">
        <summary>Funding / OI 與進階衍生（預設收合）</summary>
        <dl className="nx-kv mono sm" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <div>
            <dt className="muted">Funding</dt>
            <dd>
              {c.fundingRate == null ? "UNAVAILABLE" : `${(c.fundingRate * 100).toFixed(4)}%`}
            </dd>
          </div>
          <div>
            <dt className="muted">OI 5m</dt>
            <dd>
              {c.oiChange5mPct == null
                ? "UNAVAILABLE"
                : `${c.oiChange5mPct > 0 ? "+" : ""}${c.oiChange5mPct.toFixed(2)}%`}
            </dd>
          </div>
          <div>
            <dt className="muted">OI Value</dt>
            <dd>{c.openInterestValue == null ? "UNAVAILABLE" : c.openInterestValue}</dd>
          </div>
          <div>
            <dt className="muted">Spread</dt>
            <dd>{c.spreadBps == null ? "UNAVAILABLE" : c.spreadBps.toFixed(1)}</dd>
          </div>
        </dl>
      </details>

      <p style={{ marginTop: 16 }}>
        <Link to={`/market/${c.symbol}`}>開啟深度分析 →</Link>
      </p>
    </div>
  );
}

/**
 * V18.2.8 Opportunities — decision workspace.
 * Why now / Support / Against / Invalidation first; Funding/OI below fold.
 * Density from Account prefs drives default disclosure level (no chrome toggle).
 */
export function OpportunitiesPageV1821() {
  const { longs, shorts, loading, error, status } = useMarketScannerOverview();
  const [focusId, setFocusId] = useState<string | null>(null);
  const defaultLevel: DisclosureLevel = loadUiDensity() === "EXPERT" ? 2 : 1;
  const [level, setLevel] = useState<DisclosureLevel>(defaultLevel);

  const partitioned = partitionOpportunityCandidates([...longs, ...shorts]);
  const all = partitioned.crypto;
  const crossAsset = partitioned.crossAsset;
  const focus = all.find((c) => c.id === focusId) ?? all[0] ?? null;
  const eligibleZero =
    status?.confirmedCandidates === 0 ||
    (status?.confirmedCandidates == null && all.length === 0 && !loading);

  return (
    <div
      className="page-stack"
      style={{ display: "contents" }}
      data-testid="opportunities-v1821"
      data-non-crypto-in-crypto-opportunity-count={
        partitioned.non_crypto_symbol_in_crypto_opportunity_count
      }
    >
      <header className="v1828-ov-block" style={{ marginBottom: 0 }}>
        <h1 className="v1828-page-title">找機會</h1>
        <p className="v1828-page-sub">決策工作區 · 為何現在／支持／反對／失效優先 · 非下單建議</p>
        <div className="v1828-level-tabs" role="group" aria-label="資訊層級">
          <button
            type="button"
            className={level === 1 ? "active" : undefined}
            onClick={() => setLevel(1)}
          >
            層級 1 · 白話
          </button>
          <button
            type="button"
            className={level === 2 ? "active" : undefined}
            onClick={() => setLevel(2)}
          >
            層級 2 · 交易者
          </button>
          <button
            type="button"
            className={level === 3 ? "active" : undefined}
            onClick={() => setLevel(3)}
          >
            層級 3 · 研究
          </button>
        </div>
      </header>

      {loading ? <p className="muted v1828-ov-block">載入中…</p> : null}
      {error ? (
        <div className="nx-banner-warn v1828-ov-block">掃描器暫不可用：{error}</div>
      ) : null}

      {eligibleZero && !loading ? (
        <div
          className="v1828-ov-block"
          data-testid="no-eligible-opportunities"
          style={{ borderColor: "rgba(230, 180, 34, 0.28)" }}
        >
          <p style={{ margin: 0, fontWeight: 600 }}>目前沒有符合安全條件的市場機會</p>
          <p className="muted sm" style={{ margin: "8px 0 0" }}>
            下列若出現僅為觀察候選，不代表合格可交易機會；不暗示做多／做空可執行。
          </p>
        </div>
      ) : null}

      {crossAsset.length ? (
        <div className="nx-banner-warn v1828-ov-block" data-testid="cross-asset-context-only">
          跨資產標的（{crossAsset.map((c) => c.symbol.replace("USDT", "")).join(", ")}）·
          CROSS_ASSET_CONTEXT_ONLY · 已自加密 Opportunities 排名移除
        </div>
      ) : null}

      <div className="v1828-opp-workspace">
        <aside className="v1828-opp-list" aria-label="候選清單">
          {all.length === 0 && !loading ? (
            <p className="muted">暫無可展示候選</p>
          ) : (
            all.slice(0, 40).map((c) => (
              <button
                key={c.id}
                type="button"
                className={focus?.id === c.id ? "active" : undefined}
                data-tradable={eligibleZero ? "false" : "observe"}
                onClick={() => setFocusId(c.id)}
              >
                <span className="mono">{c.symbol.replace("USDT", "")}</span>
                {" · "}
                {STAGE_LABEL_ZH[c.stage] || c.stage}
                {" · "}
                <span className={c.side === "LONG" ? "side-long" : c.side === "SHORT" ? "side-short" : ""}>
                  {sideLabelZh(c.side)}
                </span>
              </button>
            ))
          )}
        </aside>
        {focus ? (
          <DecisionWorkspace c={focus} level={level} />
        ) : (
          <div className="v1828-opp-detail">
            <p className="muted">尚無候選可展示</p>
          </div>
        )}
      </div>
    </div>
  );
}
