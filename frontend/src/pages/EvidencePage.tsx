import { EvidenceItemCard } from "../components/EvidenceItemCard";
import { DemoDataBadge } from "../components/DemoDataBadge";
import { MembershipLockBadge } from "../components/MembershipLockBadge";
import { getEthConfirmationTimeline, getEvidence } from "../demo/nexusDataAdapter";

export function EvidencePage() {
  const items = getEvidence();
  const ethTimeline = getEthConfirmationTimeline();
  const watch = ethTimeline?.watch;
  const followup = ethTimeline?.followup;

  return (
    <div>
      <header className="page-header">
        <h1>Evidence Vault</h1>
        <DemoDataBadge />
        <MembershipLockBadge requiredTier="Pro" currentTier="Free" />
        <p className="page-sub">
          Recent AI decisions with stage markers. Sanitized snapshot · READ ONLY · NOT INVESTMENT
          ADVICE.
        </p>
      </header>

      {ethTimeline ? (
        <div className="operator-card-grid" style={{ marginBottom: "1.25rem" }}>
          <article className="panel-card operator-card">
            <div className="meta-row" style={{ marginTop: 0 }}>
              <h3 style={{ margin: 0 }}>ETH Watch Evidence</h3>
              <span className="demo-badge">SANITIZED</span>
              <DemoDataBadge />
            </div>
            <p className="mono">
              {watch?.provider} · intent={watch?.intent} · conf={watch?.confidence.toFixed(2)} ·{" "}
              {watch?.directionalBias}/{watch?.candidateSide}
            </p>
            <p className="muted">
              Triggers: entry={watch?.entryTrigger} · MAE={watch?.mae} · invalidation=
              {watch?.invalidation}
            </p>
            <p className="muted">Stage 4.18-P2B · valid_watch summary (sanitized)</p>
          </article>

          <article className="panel-card operator-card">
            <div className="meta-row" style={{ marginTop: 0 }}>
              <h3 style={{ margin: 0 }}>ETH Follow-up Evidence</h3>
              <span className="demo-badge">SANITIZED</span>
              <DemoDataBadge />
            </div>
            <p className="mono">
              {followup?.provider} · intent={followup?.intent} · conf=
              {followup?.confidence.toFixed(1)} · {followup?.directionalBias}/
              {followup?.candidateSide}
            </p>
            <p className="muted">
              Confirmation failed ·{" "}
              {ethTimeline.failureReason || "eth_followup_direction_changed"} ·{" "}
              {ethTimeline.ethDetail || "LONG/BUY → NONE/NONE"}
            </p>
            <p className="muted">
              invalidation_breached={String(ethTimeline.invalidationBreached)} · mae_breached=
              {String(ethTimeline.maeBreached)} · next={ethTimeline.nextStep}
            </p>
          </article>
        </div>
      ) : null}

      <div className="list-stack">
        {items.map((item) => (
          <EvidenceItemCard key={item.id} item={item} />
        ))}
      </div>
    </div>
  );
}
