import { ProviderComparisonCard } from "../components/ProviderComparisonCard";
import { DemoDataBadge } from "../components/DemoDataBadge";
import { MembershipLockBadge } from "../components/MembershipLockBadge";
import {
  getGraduationStatus,
  getNexusSnapshot,
  getProviderShadowSummary,
  getProviderStatus,
} from "../demo/nexusDataAdapter";

export function ProviderShadowPage() {
  const summary = getProviderShadowSummary();
  const provider = getProviderStatus();
  const grad = getGraduationStatus();
  const snap = getNexusSnapshot();
  const routing = snap.providerRoutingStatus;

  return (
    <div>
      <header className="page-header">
        <h1>Provider Shadow Center</h1>
        <DemoDataBadge />
        <MembershipLockBadge requiredTier="Elite" currentTier="Free" />
        <p className="page-sub">
          P2-R1 BTC Cerebras-first (experiment). Permanent routing change not supported.
          Actual-only graduation. Routing editor absent (forbidden).
        </p>
      </header>

      <div className="operator-card-grid" style={{ marginBottom: "1.25rem" }}>
        <article className="panel-card operator-card">
          <div className="meta-row" style={{ marginTop: 0 }}>
            <h3 style={{ margin: 0 }}>P1C Summary</h3>
            <DemoDataBadge />
          </div>
          <p>{summary.p1cSummary}</p>
          <p className="muted">Shadow diagnostics only — not graduation input.</p>
        </article>

        <article className="panel-card operator-card">
          <div className="meta-row" style={{ marginTop: 0 }}>
            <h3 style={{ margin: 0 }}>P2 Design</h3>
            <DemoDataBadge />
          </div>
          <p>{summary.p2DesignSummary}</p>
          <p className="muted">
            BTC chain experiment label: {provider.btcExperimentChain}
          </p>
          <p className="muted">
            routing_permanent_change_supported=
            {String(routing.routingPermanentChangeSupported)}
          </p>
        </article>

        <article className="panel-card operator-card">
          <div className="meta-row" style={{ marginTop: 0 }}>
            <h3 style={{ margin: 0 }}>P2-R1 BTC Cerebras-first</h3>
            <DemoDataBadge />
          </div>
          <p>{summary.p2r1Summary}</p>
          <div className="flag-grid" style={{ marginTop: "0.75rem" }}>
            <div className="flag-item">
              <div className="k">BTC graduation (actual)</div>
              <div className="v">{grad.btcGraduationCount}</div>
            </div>
            <div className="flag-item">
              <div className="k">ETH graduation (actual)</div>
              <div className="v">{grad.ethGraduationCount}</div>
            </div>
            <div className="flag-item">
              <div className="k">Shadow → graduation</div>
              <div className="v">excluded</div>
            </div>
            <div className="flag-item">
              <div className="k">actual-only graduation</div>
              <div className="v">true</div>
            </div>
            <div className="flag-item">
              <div className="k">stage_419_readiness</div>
              <div className="v">{String(grad.stage419Readiness)}</div>
            </div>
            <div className="flag-item">
              <div className="k">permanent routing</div>
              <div className="v">not supported</div>
            </div>
          </div>
        </article>
      </div>

      <ProviderComparisonCard summary={summary} />
    </div>
  );
}
