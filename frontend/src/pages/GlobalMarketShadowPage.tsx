import { useEffect, useState } from "react";
import { DemoDataBadge } from "../components/DemoDataBadge";
import { OperatorBreadcrumbs } from "../components/OperatorBreadcrumbs";
import { StatusBadge } from "../components/StatusBadge";

interface ShadowFunnel {
  marketsScanned: number;
  marketsEligible: number;
  candidatesGenerated: number;
  sixRoleReviewed: number;
  riskCriticPassed: number;
  riskCriticBlocked: number;
  portfolioSelected: number;
  openShadowPositions: number;
}

interface ShadowOverviewResponse {
  read_only?: boolean;
  exchange_write?: boolean;
  mainnet?: boolean;
  real_money?: boolean;
  mode?: string;
  labels?: string[];
  funnel?: ShadowFunnel;
  maxOpenPositions?: number;
  dataSource?: string;
}

const FIXTURE_FUNNEL: ShadowFunnel = {
  marketsScanned: 128,
  marketsEligible: 24,
  candidatesGenerated: 6,
  sixRoleReviewed: 4,
  riskCriticPassed: 2,
  riskCriticBlocked: 2,
  portfolioSelected: 1,
  openShadowPositions: 0,
};

const LAYERS = [
  {
    cadence: "3s",
    title: "Fast scan layer",
    detail: "Universe refresh · market quality gate · eligibility counts",
  },
  {
    cadence: "30s",
    title: "Review layer",
    detail: "Candidate ranking · six-role review · risk critic verdict",
  },
  {
    cadence: "3min",
    title: "Portfolio layer",
    detail: "Portfolio selection · shadow lifecycle · reflection queue",
  },
] as const;

const FUNNEL_STEPS: { key: keyof ShadowFunnel; label: string }[] = [
  { key: "marketsScanned", label: "Scanned" },
  { key: "marketsEligible", label: "Eligible" },
  { key: "candidatesGenerated", label: "Candidate" },
  { key: "sixRoleReviewed", label: "Six-role" },
  { key: "riskCriticPassed", label: "Risk Critic" },
  { key: "portfolioSelected", label: "Portfolio" },
];

export function GlobalMarketShadowPage() {
  const [overview, setOverview] = useState<ShadowOverviewResponse | null>(null);
  const [usingFixture, setUsingFixture] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const res = await fetch("/api/nexus/shadow/overview");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as ShadowOverviewResponse;
        if (!alive) return;
        setOverview(data);
        setUsingFixture(data.dataSource === "fixture" || !data.funnel);
        setLoadError(null);
      } catch (err) {
        if (!alive) return;
        setOverview(null);
        setUsingFixture(true);
        setLoadError(err instanceof Error ? err.message : "fetch_failed");
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const funnel = overview?.funnel ?? FIXTURE_FUNNEL;
  const maxPositions = overview?.maxOpenPositions ?? 2;

  return (
    <div className="page-stack">
      <OperatorBreadcrumbs
        crumbs={[
          { label: "Operator Console", to: "/overview" },
          { label: "Global Market Shadow" },
        ]}
      />
      <header className="page-header">
        <h1>Global Market Shadow Intelligence Workspace</h1>
        <StatusBadge tone="hold">SHADOW ONLY</StatusBadge>
        <StatusBadge tone="blocked">NO EXCHANGE WRITE</StatusBadge>
        <StatusBadge tone="wait">NOT REAL MONEY</StatusBadge>
        {usingFixture ? <DemoDataBadge /> : null}
        <p className="page-sub">
          Global market six-role shadow funnel · max {maxPositions} open positions · read-only
          intelligence · NOT EXECUTED · NOT INVESTMENT ADVICE
        </p>
        {loadError ? (
          <p className="muted sm">
            API unavailable ({loadError}) — showing FIXTURE demo numbers.
          </p>
        ) : null}
      </header>

      <section className="panel-card dense-card">
        <div className="meta-row" style={{ marginTop: 0 }}>
          <h3 style={{ margin: 0 }}>Safety posture</h3>
          <StatusBadge tone="pass">read_only=true</StatusBadge>
          <StatusBadge tone="pass">exchange_write=false</StatusBadge>
        </div>
        <div className="flag-grid">
          <div className="flag-item">
            <div className="k">mode</div>
            <div className="v">{overview?.mode ?? "SHADOW"}</div>
          </div>
          <div className="flag-item">
            <div className="k">mainnet</div>
            <div className="v">false</div>
          </div>
          <div className="flag-item">
            <div className="k">real money</div>
            <div className="v">false</div>
          </div>
          <div className="flag-item">
            <div className="k">max open positions</div>
            <div className="v">{maxPositions}</div>
          </div>
          <div className="flag-item">
            <div className="k">labels</div>
            <div className="v">FIXTURE · NOT_LIVE · NOT_EXECUTED</div>
          </div>
          <div className="flag-item">
            <div className="k">data source</div>
            <div className="v">{usingFixture ? "FIXTURE" : overview?.dataSource ?? "live_state"}</div>
          </div>
        </div>
      </section>

      <section className="panel-card dense-card">
        <div className="meta-row" style={{ marginTop: 0 }}>
          <h3 style={{ margin: 0 }}>Shadow funnel</h3>
          {usingFixture ? <DemoDataBadge /> : null}
        </div>
        <div className="flag-grid">
          {FUNNEL_STEPS.map((step) => (
            <div className="flag-item" key={step.key}>
              <div className="k">{step.label}</div>
              <div className="v">{funnel[step.key]}</div>
            </div>
          ))}
          <div className="flag-item">
            <div className="k">Open shadow positions</div>
            <div className="v">
              {funnel.openShadowPositions} / {maxPositions}
            </div>
          </div>
          <div className="flag-item">
            <div className="k">Risk critic blocked</div>
            <div className="v">{funnel.riskCriticBlocked}</div>
          </div>
        </div>
      </section>

      <section className="operator-section">
        <h2 className="section-title">Operational layers</h2>
        <div className="operator-card-grid">
          {LAYERS.map((layer) => (
            <article className="panel-card operator-card" key={layer.cadence}>
              <div className="meta-row" style={{ marginTop: 0 }}>
                <h3 style={{ margin: 0 }}>
                  {layer.cadence} · {layer.title}
                </h3>
                <StatusBadge tone="neutral">SHADOW</StatusBadge>
              </div>
              <p className="muted">{layer.detail}</p>
              <p className="muted sm">No Live Trade · No ARM · No Mainnet · No credential actions</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
