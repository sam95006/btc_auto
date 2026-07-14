import { ProviderComparisonCard } from "../components/ProviderComparisonCard";
import { DemoDataBadge } from "../components/DemoDataBadge";
import { GateChecklistCard } from "../components/GateChecklistCard";
import { MembershipLockBadge } from "../components/MembershipLockBadge";
import { OperatorBreadcrumbs } from "../components/OperatorBreadcrumbs";
import { PageSummaryCard } from "../components/PageSummaryCard";
import { RelatedArtifactLinks } from "../components/RelatedArtifactLinks";
import { StatusBadge } from "../components/StatusBadge";
import { PROVIDER_ROUTING_SUMMARY } from "../demo/docSummaries";
import { PROVIDER_RELATED_STAGES, ROUTING_POLICY_CHECKLIST } from "../demo/reportIndex";
import { useHashScroll } from "../hooks/useHashScroll";
import {
  getGraduationStatus,
  getNexusSnapshot,
  getProviderShadowSummary,
  getProviderStatus,
} from "../demo/nexusDataAdapter";

export function ProviderShadowPage() {
  useHashScroll();
  const summary = getProviderShadowSummary();
  const provider = getProviderStatus();
  const grad = getGraduationStatus();
  const snap = getNexusSnapshot();
  const routing = snap.providerRoutingStatus;
  const experimentSupported = routing.btcCerebrasFirstExperimentSupported ?? true;

  return (
    <div className="page-stack">
      <OperatorBreadcrumbs
        crumbs={[
          { label: "Operator Console", to: "/overview" },
          { label: "Provider Shadow" },
        ]}
      />
      <header className="page-header">
        <h1>Provider Shadow</h1>
        <StatusBadge tone="hold">HOLD</StatusBadge>
        <StatusBadge tone="pass">experiment only</StatusBadge>
        <DemoDataBadge />
        <MembershipLockBadge requiredTier="Elite" currentTier="Free" />
        <p className="page-sub">
          Routing experiment history · permanent routing change=false · shadow not used for
          graduation · future routing changes require operator approval. READ ONLY · NOT INVESTMENT
          ADVICE.
        </p>
      </header>

      <PageSummaryCard {...PROVIDER_ROUTING_SUMMARY} />

      <section className="panel-card operator-card">
        <div className="meta-row" style={{ marginTop: 0 }}>
          <h3 style={{ margin: 0 }}>Current routing posture</h3>
          <StatusBadge tone="pass">no permanent change</StatusBadge>
          <DemoDataBadge />
        </div>
        <div className="flag-grid">
          <div className="flag-item">
            <div className="k">BTC Cerebras-first</div>
            <div className="v">experiment only</div>
          </div>
          <div className="flag-item">
            <div className="k">permanent routing change</div>
            <div className="v">{String(routing.routingPermanentChangeSupported)}</div>
          </div>
          <div className="flag-item">
            <div className="k">shadow used for graduation</div>
            <div className="v">false</div>
          </div>
          <div className="flag-item">
            <div className="k">future routing changes</div>
            <div className="v">require operator approval</div>
          </div>
          <div className="flag-item">
            <div className="k">routing auto change</div>
            <div className="v">false</div>
          </div>
          <div className="flag-item">
            <div className="k">BTC Cerebras-first experiment supported</div>
            <div className="v">{String(experimentSupported)}</div>
          </div>
        </div>
        <RelatedArtifactLinks
          stages={[...PROVIDER_RELATED_STAGES]}
          label="Related docs (P2G · P2H · P2H-REL) · routing remains experimental"
        />
      </section>

      <GateChecklistCard
        title="Routing Remains Experimental"
        items={ROUTING_POLICY_CHECKLIST}
        footer="permanent routing change=false · shadow not used for graduation · no routing editor"
      />

      <div className="operator-section">
        <h2 className="section-title">Experiment history</h2>
        <div className="operator-card-grid">
          <article className="panel-card operator-card">
            <div className="meta-row" style={{ marginTop: 0 }}>
              <h3 style={{ margin: 0 }}>P1C / P2 design</h3>
              <DemoDataBadge />
            </div>
            <p>{summary.p1cSummary}</p>
            <p className="muted">{summary.p2DesignSummary}</p>
            <p className="muted">Shadow diagnostics only — not graduation input.</p>
          </article>

          <article className="panel-card operator-card">
            <div className="meta-row" style={{ marginTop: 0 }}>
              <h3 style={{ margin: 0 }}>BTC Cerebras-first chain</h3>
              <DemoDataBadge />
            </div>
            <p>{summary.p2r1Summary}</p>
            <p className="muted">chain label: {provider.btcExperimentChain}</p>
            {snap.providerShadowStatus.p2dSummary ? (
              <p className="muted">{snap.providerShadowStatus.p2dSummary}</p>
            ) : null}
            {snap.providerShadowStatus.p2dR1Summary ? (
              <p className="muted">{snap.providerShadowStatus.p2dR1Summary}</p>
            ) : null}
            {snap.providerShadowStatus.p2eSummary ? (
              <p className="muted">{snap.providerShadowStatus.p2eSummary}</p>
            ) : null}
            {snap.providerShadowStatus.p2fSummary ? (
              <p className="muted">{snap.providerShadowStatus.p2fSummary}</p>
            ) : null}
            {snap.providerShadowStatus.p2gSummary ? (
              <p className="muted">{snap.providerShadowStatus.p2gSummary}</p>
            ) : null}
            {snap.providerShadowStatus.p2hSummary ? (
              <p className="muted">{snap.providerShadowStatus.p2hSummary}</p>
            ) : null}
          </article>

          <article className="panel-card operator-card">
            <div className="meta-row" style={{ marginTop: 0 }}>
              <h3 style={{ margin: 0 }}>Graduation (actual-only)</h3>
              <StatusBadge tone="blocked">Stage 4.19 BLOCKED</StatusBadge>
              <DemoDataBadge />
            </div>
            <div className="flag-grid">
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
                <div className="k">permanent routing</div>
                <div className="v">not supported</div>
              </div>
            </div>
          </article>
        </div>
      </div>

      <ProviderComparisonCard summary={summary} />
    </div>
  );
}
