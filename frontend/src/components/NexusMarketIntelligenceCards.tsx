import { useEffect, useState } from "react";

interface MiComponent {
  id: string;
  label: string;
  score: number | null;
  classification: string;
  change: number | null;
  freshness: string;
  coverage?: number | null;
  missing?: string[];
  detail?: string;
  updatedAt?: number | null;
}

interface MiSummary {
  ok: boolean;
  error?: string;
  updatedAt?: number | null;
  components?: MiComponent[];
}

const CARD_IDS = ["market_sentiment", "altcoin_breadth", "overall_direction"] as const;

const CARD_META: Record<
  string,
  { label: string; description: string }
> = {
  market_sentiment: {
    label: "NEXUS Market Sentiment",
    description: "衍生品市場情緒指標（資金費率、持倉、多空比）",
  },
  altcoin_breadth: {
    label: "NEXUS Altcoin Breadth",
    description: "山寨幣廣度指標（相對 BTC 表現、漲跌比）",
  },
  overall_direction: {
    label: "NEXUS Overall Market Direction",
    description: "整體市場方向評估（綜合多維度輸入）",
  },
};

function freshness_label(updatedAt: number | null | undefined): string {
  if (!updatedAt) return "—";
  const diff = (Date.now() - updatedAt) / 1000;
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  return `${Math.round(diff / 3600)}h ago`;
}

function ScoreBar({ score, classification }: { score: number | null; classification: string }) {
  if (score == null) return <div className="nx-mi-score-empty muted">—</div>;
  const cls = classification.toLowerCase().replace(/[^a-z]/g, "_");
  return (
    <div className={`nx-mi-score-bar-wrap nx-mi-cls-${cls}`}>
      <div className="nx-mi-score-bar">
        <div
          className="nx-mi-score-fill"
          style={{ width: `${Math.min(100, Math.max(0, score))}%` }}
        />
      </div>
      <span className="nx-mi-score-val mono">{Math.round(score)}</span>
    </div>
  );
}

function MiCard({
  component,
  fallbackId,
}: {
  component: MiComponent | null;
  fallbackId: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const meta = CARD_META[component?.id ?? fallbackId] ?? CARD_META[fallbackId];
  const c = component;

  return (
    <article
      className={`nx-mi-card nx-mi-card-${fallbackId.replace(/_/g, "-")}`}
      aria-label={meta.label}
    >
      <div className="nx-mi-card-head">
        <div>
          <h3 className="nx-mi-label">{meta.label}</h3>
          <p className="nx-mi-desc muted sm">{meta.description}</p>
        </div>
        {c ? (
          <button
            type="button"
            className="nx-mi-expand-btn nx-text-btn muted sm"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
          >
            {expanded ? "收起" : "詳情"}
          </button>
        ) : null}
      </div>

      {c ? (
        <>
          <div className="nx-mi-body">
            <div className="nx-mi-classification">{c.classification}</div>
            <ScoreBar score={c.score} classification={c.classification} />
            <div className="nx-mi-meta-row">
              {c.change != null ? (
                <span className={`nx-mi-change ${c.change >= 0 ? "up" : "down"}`}>
                  {c.change > 0 ? "+" : ""}
                  {c.change.toFixed(1)}
                </span>
              ) : null}
              {c.coverage != null ? (
                <span className="muted sm">coverage {Math.round(c.coverage * 100)}%</span>
              ) : null}
              <span className="muted sm">{freshness_label(c.updatedAt)}</span>
              <span className={`nx-mi-fresh-badge nx-mi-fresh-${c.freshness?.toLowerCase() ?? "unknown"}`}>
                {c.freshness ?? "—"}
              </span>
            </div>
          </div>

          {expanded && (
            <div className="nx-mi-detail">
              {c.detail ? <p className="muted sm">{c.detail}</p> : null}
              {c.missing && c.missing.length > 0 ? (
                <div className="nx-mi-missing">
                  <span className="muted sm">缺少資料：</span>
                  <ul className="nx-mi-missing-list">
                    {c.missing.map((m) => (
                      <li key={m} className="muted sm">{m}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          )}
        </>
      ) : (
        <div className="nx-mi-unavailable">
          <span className="muted sm">UNAVAILABLE · API 尚未回應 · 資料累積中</span>
        </div>
      )}
    </article>
  );
}

/**
 * Phase 6.4 — NEXUS Market Intelligence summary cards.
 * Fetches /api/nexus/market-intelligence/summary.
 * Labels are explicitly NEXUS-* — never "Official Fear & Greed" or "Altseason".
 */
export function NexusMarketIntelligenceCards() {
  const [summary, setSummary] = useState<MiSummary | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await fetch("/api/nexus/market-intelligence/summary", {
          signal: AbortSignal.timeout(8000),
        });
        if (!alive) return;
        if (r.ok) {
          const data = (await r.json()) as MiSummary;
          setSummary(data);
          setLoadErr(null);
        } else {
          setLoadErr(`HTTP ${r.status}`);
          setSummary(null);
        }
      } catch (e) {
        if (!alive) return;
        setLoadErr(e instanceof Error ? e.message : "fetch_failed");
        setSummary(null);
      }
    };
    void load();
    const id = window.setInterval(() => void load(), 45_000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  // Even if API fails, render placeholders so the UI section is present
  const getComponent = (id: string): MiComponent | null =>
    summary?.components?.find((c) => c.id === id) ?? null;

  if (loadErr && !summary) {
    // API not live yet — show placeholders without error banner (graceful)
    return (
      <div className="nx-mi-cards">
        {CARD_IDS.map((id) => (
          <MiCard key={id} component={null} fallbackId={id} />
        ))}
      </div>
    );
  }

  return (
    <div className="nx-mi-cards">
      {CARD_IDS.map((id) => (
        <MiCard key={id} component={getComponent(id)} fallbackId={id} />
      ))}
    </div>
  );
}
