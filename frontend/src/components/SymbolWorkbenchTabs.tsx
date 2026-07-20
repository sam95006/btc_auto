import { useEffect, useState } from "react";
import type { MarketCandidate } from "../market/scannerApi";
import { formatUsd } from "../market/freshness";

type TabId =
  | "overview"
  | "structure"
  | "orderflow"
  | "derivatives"
  | "sentiment"
  | "ai"
  | "risk"
  | "performance";

const TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "structure", label: "Structure" },
  { id: "orderflow", label: "Order Flow" },
  { id: "derivatives", label: "Derivatives" },
  { id: "sentiment", label: "Sentiment" },
  { id: "ai", label: "AI Evidence" },
  { id: "risk", label: "Risk" },
  { id: "performance", label: "Performance" },
];

function Pending({ label }: { label: string }) {
  return (
    <p className="muted">
      {label}: <span className="tag tag-warn">UNAVAILABLE_PROVIDER_PENDING</span>
    </p>
  );
}

type Props = {
  symbol: string;
  candidate: MarketCandidate | null;
  snap: Record<string, unknown> | null;
  price?: number | null;
};

/**
 * Phase 6.5 Symbol Workbench tabs — real data when available, honest pending otherwise.
 */
export function SymbolWorkbenchTabs({ symbol, candidate, snap, price }: Props) {
  const [tab, setTab] = useState<TabId>("overview");
  const [indicators, setIndicators] = useState<Record<string, unknown> | null>(null);
  const [streamMode, setStreamMode] = useState<string>("HYBRID_POLLING");
  const [trace, setTrace] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    let alive = true;
    const sym = symbol.toUpperCase();
    Promise.all([
      fetch(`/api/nexus/markets/${encodeURIComponent(sym)}/indicators?interval=5m&limit=120`)
        .then((r) => r.json())
        .catch(() => null),
      fetch(`/api/nexus/markets/${encodeURIComponent(sym)}/stream-status`)
        .then((r) => r.json())
        .catch(() => null),
    ]).then(([ind, st]) => {
      if (!alive) return;
      if (ind?.ok && ind.indicators) setIndicators(ind.indicators);
      if (st?.streamMode) setStreamMode(String(st.streamMode));
    });
    return () => {
      alive = false;
    };
  }, [symbol]);

  useEffect(() => {
    if (!candidate?.id) return;
    let alive = true;
    fetch(`/api/nexus/candidates/${encodeURIComponent(candidate.id)}/decision-trace`)
      .then((r) => r.json())
      .then((j) => {
        if (alive) setTrace(j);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [candidate?.id]);

  const ind = indicators || {};

  return (
    <section className="nx-workbench">
      <div className="nx-workbench-tabs" role="tablist" aria-label="Symbol workbench">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            className={tab === t.id ? "active" : undefined}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="nx-workbench-panel" role="tabpanel">
        {tab === "overview" ? (
          <div className="nx-wb-grid">
            <div><span className="muted">Price</span><strong className="mono">{formatUsd(price)}</strong></div>
            <div><span className="muted">24h</span><strong className="mono">{String(snap?.change24hPct ?? candidate?.change24hPct ?? "—")}</strong></div>
            <div><span className="muted">Volume</span><strong className="mono">{String(snap?.volume24h ?? "—")}</strong></div>
            <div><span className="muted">Direction</span><strong>{candidate?.side ?? "NEUTRAL"}</strong></div>
            <div><span className="muted">Stage</span><strong>{candidate?.stage ?? "—"}</strong></div>
            <div><span className="muted">Risk</span><strong>{candidate ? Math.round(candidate.riskScore) : "—"}</strong></div>
            <div><span className="muted">Stream</span><strong className="mono">{streamMode}</strong></div>
            <div><span className="muted">Freshness</span><strong>{candidate?.freshness ?? "—"}</strong></div>
          </div>
        ) : null}

        {tab === "structure" ? (
          indicators ? (
            <dl className="nx-kv mono">
              {["ema_20", "ema_50", "vwap", "rsi_14", "macd", "atr_14", "adx_14", "bollinger_20", "supertrend_10"].map((k) => (
                <div key={k}>
                  <dt>{k}</dt>
                  <dd>{ind[k] != null ? JSON.stringify(ind[k]).slice(0, 80) : "—"}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <Pending label="Technical indicators" />
          )
        ) : null}

        {tab === "orderflow" ? (
          <div>
            <p className="muted sm">Public order-flow foundation — advanced signals remain experimental.</p>
            <dl className="nx-kv mono">
              <div><dt>Spread bps</dt><dd>{String(snap?.spreadBps ?? "—")}</dd></div>
              <div><dt>Best bid/ask</dt><dd>UNAVAILABLE_PROVIDER_PENDING</dd></div>
              <div><dt>Imbalance</dt><dd>UNAVAILABLE_PROVIDER_PENDING</dd></div>
              <div><dt>CVD</dt><dd>UNAVAILABLE_PROVIDER_PENDING</dd></div>
              <div><dt>Taker flow</dt><dd>UNAVAILABLE_PROVIDER_PENDING</dd></div>
            </dl>
            <p className="tag tag-warn">EXPERIMENTAL — not production signals</p>
          </div>
        ) : null}

        {tab === "derivatives" ? (
          <dl className="nx-kv mono">
            <div><dt>Funding</dt><dd>{String(snap?.fundingRate ?? candidate?.fundingRate ?? "—")}</dd></div>
            <div><dt>OI</dt><dd>{String(snap?.openInterest ?? "—")}</dd></div>
            <div><dt>OI value</dt><dd>{String(snap?.openInterestValue ?? "—")}</dd></div>
            <div><dt>Mark</dt><dd>{formatUsd(snap?.markPrice as number)}</dd></div>
            <div><dt>Index</dt><dd>{formatUsd(snap?.indexPrice as number)}</dd></div>
            <div><dt>Long/Short ratio</dt><dd>UNAVAILABLE_PROVIDER_PENDING</dd></div>
            <div><dt>Liquidations</dt><dd>UNAVAILABLE_PROVIDER_PENDING</dd></div>
          </dl>
        ) : null}

        {tab === "sentiment" ? (
          <Pending label="NEXUS symbol-level sentiment" />
        ) : null}

        {tab === "ai" ? (
          <div className="nx-ai-evidence">
            <h3>Level 1 — 白話結論</h3>
            <p>
              {candidate
                ? `${candidate.side} 候選 · 階段 ${candidate.stage} · 機會 ${Math.round(candidate.opportunityScore)} / 風險 ${Math.round(candidate.riskScore)}`
                : "尚無方向候選"}
            </p>
            <h3>Level 2 — 支持／反對</h3>
            <ul>
              {(candidate?.reasons || []).slice(0, 4).map((r) => (
                <li key={r}>+ {r}</li>
              ))}
              {(candidate?.conflicts || []).slice(0, 4).map((r) => (
                <li key={r} className="conflict">− {r}</li>
              ))}
            </ul>
            <h3>Level 3 — Decision Trace</h3>
            {trace?.ok ? (
              <pre className="mono muted sm">{JSON.stringify(trace.stages || trace, null, 2).slice(0, 1200)}</pre>
            ) : (
              <p className="muted">Trace pending or candidate not in review pipeline.</p>
            )}
          </div>
        ) : null}

        {tab === "risk" ? (
          <div>
            <dl className="nx-kv mono">
              <div><dt>Production max leverage</dt><dd>3x</dd></div>
              <div><dt>Production max margin</dt><dd>20 USDT</dd></div>
              <div><dt>Max open positions</dt><dd>1</dd></div>
              <div><dt>Stop / Target</dt><dd>policy-driven when position opens</dd></div>
              <div><dt>Invalidation</dt><dd>{candidate?.invalidationContext || "—"}</dd></div>
            </dl>
            <p className="tag tag-warn">DynamicRiskProposal = SHADOW ONLY — does not change production PAPER limits</p>
          </div>
        ) : null}

        {tab === "performance" ? (
          <div>
            <p className="muted">Natural PAPER metrics only — Validation／Replay streams are separated.</p>
            <Pending label="Symbol-level natural PAPER performance series" />
          </div>
        ) : null}
      </div>
    </section>
  );
}
