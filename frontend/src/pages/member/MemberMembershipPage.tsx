import { MemberPageChrome } from "../../member/MemberPageChrome";
import { membershipTiers } from "../../member/demoCatalog";

export function MemberMembershipPage() {
  return (
    <MemberPageChrome
      title="Membership"
      subtitle="Tier labels only · NO LIVE BILLING · LOCAL/STAGING · UNVALIDATED_HYPOTHESIS"
    >
      <div className="member-card-grid">
        {membershipTiers.map((tier) => (
          <article key={tier.id} className="member-panel">
            <h2>{tier.name}</h2>
            <p>{tier.blurb}</p>
            <ul>
              {tier.entitlements.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
            <p className="muted sm">{tier.billingNote}</p>
            <button type="button" className="member-btn" disabled title="No live billing">
              Not available (no billing)
            </button>
          </article>
        ))}
      </div>
    </MemberPageChrome>
  );
}
