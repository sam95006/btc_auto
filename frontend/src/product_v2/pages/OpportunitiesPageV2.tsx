import { Link } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import type { MarketCandidate } from "../../market/scannerApi";
import { displayOrPending, freshnessLabel, fmtNum } from "../../market/displayNull";
import { sideLabelZh, STAGE_LABEL_ZH, plainReason } from "../../market/scannerApi";
import { partitionOpportunityCandidates } from "../../market/cryptoOpportunityFilter";
import { formatUsd } from "../../market/freshness";
import { WatchStarButton } from "../../components/WatchStarButton";
import { memberDataTrustLabel } from "../../market/marketMetricFunnel";
import { useLiveMarketRanking } from "../useLiveMarketRanking";
import {
  filterRankingRows,
  formatRankMove,
  type LiveRankingRow,
  type RankingTab,
} from "../../market/liveMarketRanking";

function unavailable(v: unknown): boolean {
  return v == null || v === "" || (typeof v === "number" && Number.isNaN(v));
}

function fmtPct(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

const TABS: { id: RankingTab; label: string }[] = [
  { id: "ALL", label: "總榜" },
  { id: "LONG", label: "多方" },
  { id: "SHORT", label: "空方" },
  { id: "MOVE", label: "異動" },
  { id: "OI", label: "OI" },
  { id: "ACTIVITY", label: "Activity" },
  { id: "RISK", label: "風險" },
];

function EvidencePanel({ c, row }: { c: MarketCandidate | null; row: LiveRankingRow | null }) {
  if (!c && !row) return null;
  const trust = memberDataTrustLabel({
    scannerFreshness: c?.freshness || row?.freshness,
    confirmedCandidates: c?.stage === "CONFIRMED" || row?.qualified ? 1 : 0,
  });

  const rows: { label: string; value: string; muted?: boolean }[] = [
    {
      label: "Rank",
      value: row ? formatRankMove(row) : "—",
    },
    {
      label: "NEX Rank Score",
      value: row
        ? `${Math.round(Math.max(0, Math.min(100, row.rank_score)))} / 100 (${row.rank_score_version})`
        : "—",
    },
    {
      label: "Funding",
      value:
        (c?.fundingRate ?? row?.funding_rate) == null
          ? "尚無資料"
          : `${(((c?.fundingRate ?? row?.funding_rate) as number) * 100).toFixed(4)}%`,
      muted: (c?.fundingRate ?? row?.funding_rate) == null,
    },
    {
      label: "OI 5m",
      value:
        (c?.oiChange5mPct ?? row?.oi_change) == null
          ? "尚無資料"
          : `${((c?.oiChange5mPct ?? row?.oi_change) as number) > 0 ? "+" : ""}${((c?.oiChange5mPct ?? row?.oi_change) as number).toFixed(2)}%`,
      muted: (c?.oiChange5mPct ?? row?.oi_change) == null,
    },
    {
      label: "風險",
      value: unavailable(c?.riskScore ?? row?.risk_score)
        ? "尚無資料"
        : String(Math.round((c?.riskScore ?? row?.risk_score) as number)),
    },
    {
      label: "資料品質",
      value: `${trust.label_zh} · ${freshnessLabel(c?.freshness || row?.freshness) || "未知"}`,
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
        <p>{plainReason(c?.reasons?.[0] || row?.primary_reason || "結構仍在觀察", true)}</p>
      </div>
    </aside>
  );
}

function DecisionCenter({
  c,
  row,
  onBack,
}: {
  c: MarketCandidate | null;
  row: LiveRankingRow | null;
  onBack?: () => void;
}) {
  const whyNow = plainReason(c?.reasons?.[0] || row?.primary_reason || "結構仍在觀察", true);
  const supporting = (c?.reasons || [row?.primary_reason].filter(Boolean) as string[])
    .slice(0, 4)
    .map((r) => plainReason(r, true));
  const against = (c?.conflicts || []).slice(0, 4).map((r) => plainReason(r, true));
  const invalidation = displayOrPending(c?.invalidationContext, "尚無明確失效條件");
  const riskText = unavailable(c?.riskScore ?? row?.risk_score)
    ? "尚無資料"
    : fmtNum(c?.riskScore ?? row?.risk_score);
  const stage = c?.stage || row?.stage;
  const side = c?.side || row?.side_bias;
  const nowLine = `${side ? sideLabelZh(side) : "—"} · ${
    stage ? STAGE_LABEL_ZH[stage] || stage : "—"
  } · ${freshnessLabel(c?.freshness || row?.freshness) || "更新未知"}`;

  return (
    <div className="mp2-opp-center" data-testid="opp-decision-workspace">
      {onBack ? (
        <button type="button" className="mp2-btn mp2-btn-ghost mobile-only" onClick={onBack}>
          ← 返回清單
        </button>
      ) : null}

      <header style={{ marginBottom: 8 }}>
        <Link
          to={`/market/${(c?.symbol || row?.symbol || "").toUpperCase()}`}
          className="mono"
          style={{ fontSize: "1.35rem", fontWeight: 650, color: "var(--mp2-ink)" }}
        >
          {(c?.symbol || row?.symbol || "").replace("USDT", "")}
        </Link>
        <p className="muted" style={{ margin: "4px 0 0", fontSize: "0.875rem" }}>
          {nowLine}
          {row ? ` · ${formatRankMove(row)}` : ""}
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
        <p
          className={
            unavailable(c?.riskScore ?? row?.risk_score)
              ? "muted"
              : ((c?.riskScore ?? row?.risk_score) as number) >= 70
                ? "neg"
                : undefined
          }
        >
          {riskText}
        </p>
      </div>

      {row ? (
        <div className="mp2-decision-block">
          <h3>排名分數</h3>
          <dl
            className="mono"
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 8,
              fontSize: "0.875rem",
              margin: 0,
            }}
          >
            <div>
              <dt className="muted">Score</dt>
              <dd style={{ margin: 0 }}>{Math.round(Math.max(0, Math.min(100, row.rank_score)))}</dd>
            </div>
            <div>
              <dt className="muted">機會</dt>
              <dd style={{ margin: 0 }}>{Math.round(row.rank_score_components.opportunity)}</dd>
            </div>
            <div>
              <dt className="muted">確認</dt>
              <dd style={{ margin: 0 }}>{Math.round(row.rank_score_components.confirmation)}</dd>
            </div>
            <div>
              <dt className="muted">價格</dt>
              <dd style={{ margin: 0 }}>{row.price == null ? "尚無資料" : formatUsd(row.price)}</dd>
            </div>
          </dl>
        </div>
      ) : null}

      <div className="mp2-actions">
        <Link to="/alerts" className="mp2-btn mp2-btn-primary">
          設警報
        </Link>
        {(c?.symbol || row?.symbol) && <WatchStarButton symbol={(c?.symbol || row?.symbol)!} />}
        <Link to={`/market/${(c?.symbol || row?.symbol || "").toUpperCase()}`} className="mp2-btn">
          市場終端
        </Link>
      </div>
    </div>
  );
}

/**
 * Product V2 Discover / Live Radar — replaces Opportunities L1/L2/L3 UI.
 * Route remains /opportunities for parity (label: 探索).
 */
export function OpportunitiesPageV2() {
  const ranking = useLiveMarketRanking();
  const { candidates, loading, error, status, qualified_count, radar, rows, closest_watch } = ranking;
  const [tab, setTab] = useState<RankingTab>("ALL");
  const [focusSym, setFocusSym] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(true);
  const [mobileDetail, setMobileDetail] = useState(false);

  const partitioned = partitionOpportunityCandidates(candidates);
  const display = useMemo(() => filterRankingRows(radar.length ? radar : rows, tab), [radar, rows, tab]);

  const focusRow = display.find((r) => r.symbol === focusSym) ?? display[0] ?? null;
  const focusCand =
    partitioned.crypto.find((c) => c.symbol === focusRow?.symbol) ??
    candidates.find((c) => c.symbol === focusRow?.symbol) ??
    null;

  const eligibleZero =
    (status?.confirmedCandidates === 0 || status?.confirmedCandidates == null) &&
    qualified_count === 0;

  useEffect(() => {
    if (!focusSym && display[0]) setFocusSym(display[0].symbol);
  }, [display, focusSym]);

  const selectRow = (sym: string) => {
    setFocusSym(sym);
    setMobileDetail(true);
  };

  return (
    <div
      data-testid="product-v2-opportunities"
      data-nexus-product-generation="2"
      data-discover="1"
      data-l1-l2-l3="removed"
      data-non-crypto-in-crypto-opportunity-count={partitioned.non_crypto_symbol_in_crypto_opportunity_count}
      data-ranking-qualified={qualified_count}
    >
      <header style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-start" }}>
        <div style={{ flex: 1, minWidth: 200 }}>
          <h1 className="mp2-page-title">探索</h1>
          <p className="mp2-page-sub">Live Radar · 發現值得注意的市場</p>
        </div>
        <button
          type="button"
          className="mp2-btn desktop-only"
          onClick={() => setDrawerOpen((v) => !v)}
          aria-pressed={drawerOpen}
        >
          {drawerOpen ? "收合證據" : "展開證據"}
        </button>
      </header>

      <div className="mp2-chip-row" role="tablist" aria-label="探索分頁" style={{ marginTop: 10 }}>
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={tab === t.id ? "active" : undefined}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error ? <div className="mp2-banner">{error}</div> : null}
      {eligibleZero ? (
        <div className="mp2-empty" data-testid="no-eligible-opportunities">
          合格機會為 0；下方為 Live Radar 觀察排名（非可交易推薦）。
        </div>
      ) : null}

      <div
        className={`mp2-opp${drawerOpen ? "" : " no-evidence"}${mobileDetail ? " mobile-detail" : " mobile-list"}`}
      >
        <nav className="mp2-opp-nav" aria-label="Live Radar 導覽">
          <p className="mp2-kicker">
            Radar {display.length} · 合格 {qualified_count}
          </p>
          {loading && !display.length ? (
            <div className="mp2-skeleton-stack" aria-busy="true">
              <div className="mp2-skeleton" style={{ height: 40 }} />
              <div className="mp2-skeleton" style={{ height: 40 }} />
            </div>
          ) : null}
          {!loading && !display.length ? (
            <div className="mp2-empty" data-testid="radar-empty">
              <p>目前沒有明顯市場異動</p>
              {closest_watch.length ? (
                <div className="mp2-closest-watch" data-testid="closest-watch">
                  <p className="mp2-kicker">Closest Watch</p>
                  {closest_watch.map((r) => (
                    <button
                      key={r.candidate_id}
                      type="button"
                      className="mp2-opp-nav-item"
                      onClick={() => selectRow(r.symbol)}
                    >
                      <span className="sym">{r.symbol.replace("USDT", "")}</span>
                      <span className="meta">{STAGE_LABEL_ZH[r.stage] || r.stage}</span>
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
          {display.map((r) => (
            <button
              key={r.candidate_id}
              type="button"
              className={`mp2-opp-nav-item${focusRow?.symbol === r.symbol ? " is-active" : ""}`}
              onClick={() => selectRow(r.symbol)}
            >
              <span className="sym">
                #{r.rank} {r.symbol.replace("USDT", "")}
              </span>
              <span className="meta">
                {sideLabelZh(r.side_bias)} · {STAGE_LABEL_ZH[r.stage] || r.stage} ·{" "}
                {formatRankMove(r)} · {fmtPct(r.change_24h)}
              </span>
            </button>
          ))}
        </nav>

        {focusRow || focusCand ? (
          <DecisionCenter
            c={focusCand}
            row={focusRow}
            onBack={() => setMobileDetail(false)}
          />
        ) : (
          <div className="mp2-opp-center">
            <p className="muted">選擇左側標的以檢視</p>
          </div>
        )}

        {drawerOpen && (focusCand || focusRow) ? (
          <EvidencePanel c={focusCand} row={focusRow} />
        ) : null}
      </div>
    </div>
  );
}
