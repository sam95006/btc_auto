import { DemoDataBadge } from "../components/DemoDataBadge";
import { MembershipLockBadge } from "../components/MembershipLockBadge";
import { getMembershipTiers } from "../demo/nexusDataAdapter";

export function MembershipPage() {
  const tiers = getMembershipTiers();

  return (
    <div>
      <header className="page-header">
        <h1>Membership Center</h1>
        <DemoDataBadge />
        <p className="page-sub">
          Free → Standard → Pro → Elite → Team → Enterprise. UI lock stubs only — no billing.
        </p>
      </header>
      <div className="card-grid">
        {tiers.map((t) => (
          <article key={t.tier} className="panel-card">
            <div className="meta-row" style={{ marginTop: 0 }}>
              <h3 style={{ margin: 0 }}>{t.label}</h3>
              <DemoDataBadge />
            </div>
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
