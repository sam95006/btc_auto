import { MemberPageChrome } from "../../member/MemberPageChrome";
import { LiveSlotStrip, usePageSlots } from "../../member/LiveSlotStrip";

export function MemberMembershipPage() {
  const { loading, items } = usePageSlots([
    ["membership.tier_card", "availability", "Tier availability"],
    ["membership.entitlement_chip", "qual", "Entitlement"],
    ["membership.billing_note_card", "event", "Billing note"],
  ]);

  return (
    <MemberPageChrome title="Membership" subtitle="Tier labels · NO LIVE BILLING · LOCAL/STAGING">
      {loading ? <p className="muted">Loading live bindings...</p> : null}
      <LiveSlotStrip bindings={items} />
      <p className="muted sm">
        Live billing disabled · entitlements never grant private execution access.
      </p>
    </MemberPageChrome>
  );
}
