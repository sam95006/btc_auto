import { useEffect, useState } from "react";
import { BybitDemoAutonomousCard } from "../components/BybitDemoAutonomousCard";
import { fetchFounderOperatorSnapshot } from "./api";
import type { FounderOperatorPanel, FounderOperatorSnapshot } from "./types";
import { FOUNDER_OPERATOR_NAV } from "./types";

function healthClass(health: string): string {
  const h = health.toUpperCase();
  if (h === "OK" || h === "ARMED_READINESS") return "ok";
  if (h.includes("BLOCK") || h.includes("FAIL")) return "bad";
  return "warn";
}

function PanelCard({ panel }: { panel: FounderOperatorPanel }) {
  const metrics = Object.entries(panel.metrics || {});
  const binding = panel.binding;
  return (
    <section className="nx-card nx-founder-panel" id={panel.id} aria-label={panel.title}>
      <div className="nx-founder-panel-head">
        <h2>{panel.title}</h2>
        <span className={`tag tag-${healthClass(panel.health)}`}>{panel.health}</span>
      </div>
      <p className="muted sm">{panel.summary}</p>
      {binding ? (
        <div className="nx-founder-binding" aria-label="Surface binding">
          <span className={`tag tag-${binding.mode === "LIVE" ? "ok" : "warn"}`}>
            bind={binding.mode}
          </span>
          <span className="muted sm mono">{binding.sourceSurface}</span>
          <span className="muted sm mono">asOf={binding.asOf || "—"}</span>
          <span className="muted sm mono">lineage={binding.lineageId.slice(0, 10)}</span>
        </div>
      ) : null}
      <dl className="nx-founder-metrics">
        {metrics.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd className="mono">{v === null || v === undefined ? "—" : String(v)}</dd>
          </div>
        ))}
      </dl>
      {panel.notes?.length ? (
        <ul className="nx-founder-notes muted sm">
          {panel.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      ) : null}
      <div className="tag">read-only · memberVisible={String(panel.memberVisible)}</div>
    </section>
  );
}

/**
 * Founder Private Operator overview — live/sim bound capture → kill-switch panels.
 */
export function FounderOperatorPage() {
  const [snap, setSnap] = useState<FounderOperatorSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const result = await fetchFounderOperatorSnapshot();
      if (cancelled) return;
      setLoading(false);
      if (!result.ok) {
        setError(("error" in result && result.error) || "operator_denied");
        setSnap(null);
        return;
      }
      setSnap(result as FounderOperatorSnapshot);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <div className="page-stack nx-founder-operator">
        <p className="muted">載入 Founder Operator 快照…</p>
      </div>
    );
  }

  if (error || !snap) {
    return (
      <div className="page-stack nx-founder-operator" role="alert">
        <h1>Operator Access Denied</h1>
        <p className="muted">會員工作階段無法讀取私有營運資料。</p>
        <div className="tag tag-warn">{error || "denied"}</div>
      </div>
    );
  }

  return (
    <div className="page-stack nx-founder-operator">
      <header>
        <h1>Founder Private Operator</h1>
        <p className="muted">
          私有營運觀測 · live/sim bound · {snap.actor.tier} · {snap.actor.identitySource} ·{" "}
          {snap.generatedAt}
        </p>
        <div className="nx-founder-banner-row">
          <span className="tag tag-warn">founder-only</span>
          <span className="tag">researchOnly={String(snap.researchOnly)}</span>
          <span className="tag">exchangeWrite={String(snap.exchangeWriteEnabled)}</span>
          <span className="tag">memberAccessible={String(snap.memberAccessible)}</span>
          {snap.bindings ? (
            <span className="tag">
              binds L{snap.bindings.liveCount}/S{snap.bindings.simulatedCount}
            </span>
          ) : null}
        </div>
      </header>

      <section className="nx-card" aria-label="Hard bans">
        <h2 className="sm">Hard bans (this surface)</h2>
        <div className="nx-founder-ban-chips">
          {snap.hardBans.map((b) => (
            <span key={b} className="tag">
              {b}
            </span>
          ))}
        </div>
      </section>

      <nav className="nx-founder-jump" aria-label="Panel jump">
        {FOUNDER_OPERATOR_NAV.map((item) => (
          <a key={item.id} href={item.hash}>
            {item.label}
          </a>
        ))}
      </nav>

      <div className="nx-founder-panel-grid">
        {snap.panels.map((p) => (
          <PanelCard key={p.id} panel={p} />
        ))}
      </div>

      <section className="nx-card" aria-label="Founder runtime observability">
        <h2 className="sm">Runtime observability (shadow / demo labels only)</h2>
        <p className="muted sm">無下單、無 ARM、無 mainnet 控件 · 僅 Founder 授權後可見</p>
        <BybitDemoAutonomousCard />
      </section>

      <p className="muted sm">{snap.note}</p>
    </div>
  );
}
