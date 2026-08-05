import { useT } from "../../i18n";
import { MemberPageChrome } from "../../member/MemberPageChrome";
import { LiveSlotStrip, usePageSlots } from "../../member/LiveSlotStrip";

export function MemberMembershipPage() {
  const t = useT();
  return (
    <MemberPageChrome
      titleKey="pages.membership.title"
      subtitleKey="pages.membership.subtitle"
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
            <button type="button" className="member-btn" disabled title={t("pages.membership.noBilling")}>
              Not available (no billing)
            </button>
          </article>
        ))}
      </div>

    </MemberPageChrome>
  );
}
