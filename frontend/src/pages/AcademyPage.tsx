import { DemoDataBadge } from "../components/DemoDataBadge";
import { MembershipLockBadge } from "../components/MembershipLockBadge";

const TRACKS = [
  { tier: "Free", title: "Risk literacy basics", locked: false },
  { tier: "Standard", title: "Round table & observation language", locked: true },
  { tier: "Pro", title: "Paper lab & reflection loops", locked: true },
] as const;

export function AcademyPage() {
  return (
    <div>
      <header className="page-header">
        <h1>NEXUS Academy</h1>
        <DemoDataBadge />
        <p className="page-sub">Curriculum stubs — Free / Standard / Pro tracks.</p>
      </header>
      <div className="card-grid">
        {TRACKS.map((t) => (
          <article key={t.tier} className="panel-card">
            <div className="meta-row" style={{ marginTop: 0 }}>
              <h3 style={{ margin: 0 }}>{t.tier}</h3>
              <DemoDataBadge />
            </div>
            <p>{t.title}</p>
            {t.locked ? (
              <MembershipLockBadge
                requiredTier={t.tier === "Standard" ? "Standard" : "Pro"}
                currentTier="Free"
              />
            ) : (
              <p className="muted">Available on Free</p>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}
