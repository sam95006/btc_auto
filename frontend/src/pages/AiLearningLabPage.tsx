import { useEffect, useState } from "react";
import { OperatorBreadcrumbs } from "../components/OperatorBreadcrumbs";
import { StatusBadge } from "../components/StatusBadge";

interface LearningOverviewResponse {
  read_only?: boolean;
  exchange_write?: boolean;
  mainnet?: boolean;
  real_money?: boolean;
  mode?: string;
  labels?: string[];
  fixed_leverage?: number;
  ai_can_change_leverage?: boolean;
  target_net_oos_win_rate?: number;
  target_status?: string;
  data_status?: string;
  data_source?: string;
  dataSource?: string;
  freshness?: string;
  providerStatus?: string;
  counts?: {
    trade_cases?: number;
    failures?: number;
    mistakes?: number;
    reflections?: number;
    proposals?: number;
    patches?: number;
    experiments?: number;
  };
}

const LAYERS = [
  {
    cadence: "3s",
    title: "Pre-trade guard",
    detail: "Mistake similarity · recurring error escalation · fixed 25x leverage",
  },
  {
    cadence: "30s",
    title: "Reflection layer",
    detail: "Failure taxonomy · counterfactuals · executable learning proposals",
  },
  {
    cadence: "3min",
    title: "Policy layer",
    detail: "Champion/challenger · shadow promotion gate · metrics truthfulness",
  },
] as const;

const FIXED_LEVERAGE = 25;

export function AiLearningLabPage() {
  const [overview, setOverview] = useState<LearningOverviewResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const res = await fetch("/api/nexus/shadow/learning/overview");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as LearningOverviewResponse;
        if (!alive) return;
        setOverview(data);
        setLoadError(null);
      } catch (err) {
        if (!alive) return;
        setOverview(null);
        setLoadError(err instanceof Error ? err.message : "fetch_failed");
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const dataStatus = overview?.data_status ?? (loadError ? "UNAVAILABLE" : "NO_DATA");
  const dataSource = overview?.data_source ?? overview?.dataSource ?? "NONE";
  const isNoData = dataStatus === "NO_DATA" || dataStatus === "UNAVAILABLE" || dataSource === "NONE";
  const targetStatus = overview?.target_status ?? "INSUFFICIENT_SAMPLE";
  const counts = overview?.counts ?? {};

  return (
    <div className="page-stack">
      <OperatorBreadcrumbs
        crumbs={[
          { label: "Operator Console", to: "/overview" },
          { label: "AI Learning Lab" },
        ]}
      />
      <header className="page-header">
        <h1>AI Learning Lab — Wave 3 Adaptive Policy</h1>
        <StatusBadge tone="hold">SHADOW ONLY</StatusBadge>
        <StatusBadge tone="blocked">NO EXCHANGE WRITE</StatusBadge>
        <StatusBadge tone="wait">NOT REAL MONEY</StatusBadge>
        <StatusBadge tone="neutral">FIXED {FIXED_LEVERAGE}X</StatusBadge>
        {isNoData ? <StatusBadge tone="wait">NO_DATA</StatusBadge> : null}
        <p className="page-sub">
          Adaptive learning policy workspace · immutable 25x leverage · read-only shadow metrics · NOT EXECUTED
        </p>
        {loadError ? (
          <p className="muted sm">API unavailable ({loadError}) — showing NO_DATA empty state.</p>
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
            <div className="k">fixed leverage</div>
            <div className="v">{overview?.fixed_leverage ?? FIXED_LEVERAGE}x (immutable)</div>
          </div>
          <div className="flag-item">
            <div className="k">AI can change leverage</div>
            <div className="v">{String(overview?.ai_can_change_leverage ?? false)}</div>
          </div>
          <div className="flag-item">
            <div className="k">target OOS win rate</div>
            <div className="v">
              {isNoData
                ? "60% · NO_DATA"
                : `${Math.round((overview?.target_net_oos_win_rate ?? 0.6) * 100)}% · ${targetStatus}`}
            </div>
          </div>
          <div className="flag-item">
            <div className="k">data status</div>
            <div className="v">{dataStatus}</div>
          </div>
          <div className="flag-item">
            <div className="k">data source</div>
            <div className="v">{dataSource}</div>
          </div>
          <div className="flag-item">
            <div className="k">freshness</div>
            <div className="v">{overview?.freshness ?? "UNAVAILABLE"}</div>
          </div>
        </div>
      </section>

      <section className="panel-card dense-card">
        <div className="meta-row" style={{ marginTop: 0 }}>
          <h3 style={{ margin: 0 }}>Learning counts</h3>
          {isNoData ? <StatusBadge tone="wait">NO_DATA · NOT SYNTHETIC</StatusBadge> : null}
        </div>
        <div className="flag-grid">
          {(
            [
              ["trade_cases", "Trade cases"],
              ["failures", "Failures"],
              ["mistakes", "Mistakes"],
              ["reflections", "Reflections"],
              ["proposals", "Proposals"],
              ["patches", "Patches"],
              ["experiments", "Experiments"],
            ] as const
          ).map(([key, label]) => (
            <div className="flag-item" key={key}>
              <div className="k">{label}</div>
              <div className="v">{isNoData ? "0 · NO_DATA" : String(counts[key] ?? 0)}</div>
            </div>
          ))}
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
              <p className="muted sm">No Live Trade · Fixed 25X · No credential actions</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
