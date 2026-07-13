import { DemoDataBadge } from "../components/DemoDataBadge";
import { MembershipLockBadge } from "../components/MembershipLockBadge";
import { getMembershipTiers, getPrivateOperatorMode } from "../demo/nexusDataAdapter";

export function MembershipPage() {
  const tiers = getMembershipTiers();
  const op = getPrivateOperatorMode();

  return (
    <div>
      <header className="page-header">
        <h1>Membership Center</h1>
        <DemoDataBadge />
        <p className="page-sub">
          Future Public SaaS architecture labels only. {op.publicSaas}. Private Operator Mode is
          the active product surface — not a customer membership product.
        </p>
      </header>

      <div className="operator-banner" role="status" style={{ marginBottom: "1.25rem" }}>
        <span className="operator-banner-label">Future Public SaaS</span>
        <span className="operator-banner-sep">·</span>
        <span>Future only / Not implemented / No billing</span>
        <DemoDataBadge />
      </div>

      <div className="card-grid">
        {tiers.map((t) => (
          <article key={t.tier} className="panel-card">
            <div className="meta-row" style={{ marginTop: 0 }}>
              <h3 style={{ margin: 0 }}>{t.label}</h3>
              <DemoDataBadge />
            </div>
            <p className="future-tier-tag">{t.productBoundary}</p>
            <p>{t.summary}</p>
            {t.lockedSurfaces.length > 0 ? (
              <>
                <p className="muted">Locked surfaces (example):</p>
                <ul>
                  {t.lockedSurfaces.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="muted">No additional UI locks in demo matrix</p>
            )}
            {t.tier !== "Free" ? (
              <MembershipLockBadge requiredTier={t.tier} currentTier="Free" />
            ) : null}
          </article>
        ))}
      </div>
    </div>
  );
}
