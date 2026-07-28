import { useEffect, useState } from "react";
import type { MarketCandidate } from "../market/scannerApi";
import { formatUsd } from "../market/freshness";
import { displayOrPending, fmtNum, fmtPctNull } from "../market/displayNull";

type TabId =
  | "overview"
  | "structure"
  | "flows"
  | "six_roles"
  | "risk"
  | "plan"
  | "memory"
  | "evidence";

const TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "structure", label: "Structure" },
  { id: "flows", label: "Flows" },
  { id: "six_roles", label: "Six Roles" },
  { id: "risk", label: "Risk" },
  { id: "plan", label: "Plan" },
  { id: "memory", label: "Memory" },
  { id: "evidence", label: "Evidence" },
];

const TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"] as const;

function Pending({ label }: { label: string }) {
  return (
    <p className="muted">
      {label}：<span className="tag tag-warn">UNAVAILABLE_PROVIDER_PENDING</span>
    </p>
  );
}

function NullVal({ v, pending = "資料尚不可用" }: { v: unknown; pending?: string }) {
  if (v == null || v === "") return <span className="muted">{pending}</span>;
  return <span>{String(v)}</span>;
}

type Props = {
  symbol: string;
  candidate: MarketCandidate | null;
  snap: Record<string, unknown> | null;
  price?: number | null;
};

/**
 * Product 7 Symbol Workbench — 8 tabs + timeframe + honest pending providers.
 */
export function SymbolWorkbenchTabs({ symbol, candidate, snap, price }: Props) {
  const [tab, setTab] = useState<TabId>("overview");
  const [tf, setTf] = useState<(typeof TIMEFRAMES)[number]>("5m");
  const [indicators, setIndicators] = useState<Record<string, unknown> | null>(null);
  const [indPending, setIndPending] = useState(false);
  const [streamMode, setStreamMode] = useState<string | null>(null);
  const [trace, setTrace] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    let alive = true;
    setIndPending(true);
    setIndicators(null);
    const sym = symbol.toUpperCase();
    Promise.all([
      fetch(
        `/api/nexus/markets/${encodeURIComponent(sym)}/indicators?interval=${encodeURIComponent(tf)}&limit=120`,
      )
        .then((r) => r.json())
        .catch(() => null),
      fetch(`/api/nexus/markets/${encodeURIComponent(sym)}/stream-status`)
        .then((r) => r.json())
        .catch(() => null),
    ]).then(([ind, st]) => {
      if (!alive) return;
      if (ind?.ok && ind.indicators) setIndicators(ind.indicators);
      else setIndicators(null);
      if (st?.streamMode) setStreamMode(String(st.streamMode));
      else setStreamMode(null);
      setIndPending(false);
    });
    return () => {
      alive = false;
    };
  }, [symbol, tf]);

  useEffect(() => {
    if (!candidate?.id) {
      setTrace(null);
      return;
    }
    let alive = true;
    fetch(`/api/nexus/candidates/${encodeURIComponent(candidate.id)}/decision-trace`)
      .then((r) => r.json())
      .then((j) => {
        if (alive) setTrace(j);
      })
      .catch(() => {
        if (alive) setTrace(null);
      });
    return () => {
      alive = false;
    };
  }, [candidate?.id]);

  const ind = indicators || {};
  const direction = candidate?.side ?? "NEUTRAL";

  return (
    <section className="nx-workbench nx-workbench-p7">
      <div className="nx-wb-toolbar">
        <div className="nx-tf-selector" role="group" aria-label="Timeframe">
          {TIMEFRAMES.map((t) => (
            <button
              key={t}
              type="button"
              className={tf === t ? "active" : undefined}
              aria-pressed={tf === t}
              onClick={() => setTf(t)}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="nx-wb-meta muted sm">
          <span>新鮮度 {candidate?.freshness || "未知"}</span>
          <span>
            Provider{" "}
            {streamMode ? (
              <span className="mono">{streamMode}</span>
            ) : (
              <span className="tag tag-warn">pending</span>
            )}
          </span>
        </div>
      </div>

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
            <div>
              <span className="muted">價格</span>
              <strong className="mono">{formatUsd(price)}</strong>
            </div>
            <div>
              <span className="muted">24h</span>
              <strong className="mono">
                {fmtPctNull(
                  (snap?.change24hPct as number | null | undefined) ?? candidate?.change24hPct,
                )}
              </strong>
            </div>
            <div>
              <span className="muted">成交量</span>
              <strong className="mono">
                <NullVal v={snap?.volume24h} />
              </strong>
            </div>
            <div>
              <span className="muted">多空傾向</span>
              <strong>{direction}</strong>
            </div>
            <div>
              <span className="muted">階段</span>
              <strong>{candidate?.stage ?? "—"}</strong>
            </div>
            <div>
              <span className="muted">風險</span>
              <strong>{fmtNum(candidate?.riskScore)}</strong>
            </div>
            <div>
              <span className="muted">關鍵位</span>
              <strong className="muted">資料尚不可用</strong>
            </div>
            <div>
              <span className="muted">失效條件</span>
              <strong>{displayOrPending(candidate?.invalidationContext, "尚未提供")}</strong>
            </div>
          </div>
        ) : null}

        {tab === "structure" ? (
          indPending ? (
            <p className="muted">指標載入中（{tf}）…</p>
          ) : indicators ? (
            <dl className="nx-kv mono">
              {[
                "ema_20",
                "ema_50",
                "vwap",
                "rsi_14",
                "macd",
                "atr_14",
                "adx_14",
                "bollinger_20",
                "supertrend_10",
              ].map((k) => (
                <div key={k}>
                  <dt>{k}</dt>
                  <dd>{ind[k] != null ? JSON.stringify(ind[k]).slice(0, 80) : "—"}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <Pending label={`技術指標（${tf}）`} />
          )
        ) : null}

        {tab === "flows" ? (
          <div>
            <p className="muted sm">Flows — orderflow + derivatives context</p>
            <dl className="nx-kv mono">
              <div>
                <dt>Spread bps</dt>
                <dd>
                  <NullVal v={snap?.spreadBps ?? candidate?.spreadBps} />
                </dd>
              </div>
              <div>
                <dt>Funding</dt>
                <dd>
                  <NullVal v={snap?.fundingRate ?? candidate?.fundingRate} />
                </dd>
              </div>
              <div>
                <dt>OI value</dt>
                <dd>
                  <NullVal v={snap?.openInterestValue ?? candidate?.openInterestValue} />
                </dd>
              </div>
              <div>
                <dt>CVD</dt>
                <dd>
                  <span className="tag tag-warn">UNAVAILABLE_PROVIDER_PENDING</span>
                </dd>
              </div>
              <div>
                <dt>Taker flow</dt>
                <dd>
                  <span className="tag tag-warn">UNAVAILABLE_PROVIDER_PENDING</span>
                </dd>
              </div>
            </dl>
            <p className="tag tag-warn">EXPERIMENTAL — not production signals</p>
          </div>
        ) : null}

        {tab === "six_roles" ? (
          <div>
            <p className="muted sm">Six-role shadow verdicts — wired to global shadow pipeline when available.</p>
            <dl className="nx-kv mono">
              {["Trend", "Momentum", "Liquidity", "Funding", "Risk", "Execution"].map((role) => (
                <div key={role}>
                  <dt>{role}</dt>
                  <dd>
                    <span className="tag tag-warn">NO_DATA</span>
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        ) : null}

        {tab === "plan" ? (
          <div>
            <p className="muted">Trade plan context — read-only · no live actions</p>
            <Pending label="Symbol-level plan draft" />
          </div>
        ) : null}

        {tab === "memory" ? (
          <div>
            <p className="muted">Learning memory / reflection hooks — shadow only</p>
            <Pending label="Symbol memory graph" />
          </div>
        ) : null}

        {tab === "evidence" ? (
          <div className="nx-ai-evidence">
            <h3>結論</h3>
            <p>
              {candidate
                ? `${candidate.side} 候選 · 階段 ${candidate.stage} · 機會 ${fmtNum(candidate.opportunityScore)} / 風險 ${fmtNum(candidate.riskScore)}`
                : "尚無方向候選"}
            </p>
            <h3>Supporting Evidence</h3>
            <ul>
              {(candidate?.reasons || []).slice(0, 4).map((r) => (
                <li key={r}>+ {r}</li>
              ))}
              {!candidate?.reasons?.length ? <li className="muted">尚無</li> : null}
            </ul>
            <h3>Contradicting Evidence</h3>
            <ul>
              {(candidate?.conflicts || []).slice(0, 4).map((r) => (
                <li key={r} className="conflict">
                  − {r}
                </li>
              ))}
              {!candidate?.conflicts?.length ? <li className="muted">尚無明顯反方</li> : null}
            </ul>
            <h3>Invalidation</h3>
            <p>{displayOrPending(candidate?.invalidationContext, "失效條件尚未提供")}</p>
            <h3>Freshness</h3>
            <p>{candidate?.freshness || "更新時間未知"}</p>
            <h3>Decision Trace</h3>
            {trace?.ok ? (
              <pre className="mono muted sm">
                {JSON.stringify(trace.stages || trace, null, 2).slice(0, 1200)}
              </pre>
            ) : (
              <p className="muted">Trace pending 或候選尚未進入 review pipeline。</p>
            )}
          </div>
        ) : null}

        {tab === "risk" ? (
          <div>
            <dl className="nx-kv mono">
              <div>
                <dt>Shadow leverage label</dt>
                <dd>25x</dd>
              </div>
              <div>
                <dt>Max shadow positions</dt>
                <dd>2</dd>
              </div>
              <div>
                <dt>Production max leverage</dt>
                <dd>3x</dd>
              </div>
              <div>
                <dt>Production max margin</dt>
                <dd>20 USDT</dd>
              </div>
              <div>
                <dt>Max open positions</dt>
                <dd>1</dd>
              </div>
              <div>
                <dt>Stop / Target</dt>
                <dd>policy-driven when position opens</dd>
              </div>
              <div>
                <dt>Invalidation</dt>
                <dd>{displayOrPending(candidate?.invalidationContext, "尚未提供")}</dd>
              </div>
            </dl>
            <p className="tag tag-warn">
              DynamicRiskProposal = SHADOW ONLY — does not change production PAPER limits
            </p>
          </div>
        ) : null}
      </div>
    </section>
  );
}
