import { MemberPageChrome } from "../../member/MemberPageChrome";
import { LiveSlotStrip, usePageSlots } from "../../member/LiveSlotStrip";
import {
  MEMBER_BUYABLE_PRODUCTS,
  MEMBER_FORBIDDEN_PRODUCTS,
} from "../../member/subscription/productBoundary";

export function MemberMembershipPage() {
  const { loading, items } = usePageSlots([
    ["membership.tier_card", "availability", "Tier availability"],
    ["membership.entitlement_chip", "qual", "Entitlement"],
    ["membership.billing_note_card", "event", "Billing note"],
  ]);

  return (
    <MemberPageChrome titleKey="pages.membership.title" subtitleKey="pages.membership.subtitle">
      {loading ? <p className="muted">Loading live bindings...</p> : null}
      <LiveSlotStrip bindings={items} />
      <section className="membership-product-boundary" aria-label="Subscription product boundary">
        <h2 className="h3">Members may buy</h2>
        <ul>
          {MEMBER_BUYABLE_PRODUCTS.map((p) => (
            <li key={p.productId}>{p.label}</li>
          ))}
        </ul>
        <h2 className="h3">Members do not buy</h2>
        <ul>
          {MEMBER_FORBIDDEN_PRODUCTS.map((p) => (
            <li key={p.productId}>{p.label}</li>
          ))}
        </ul>
      </section>
      <p className="muted sm">
        Live billing disabled · entitlements never grant private execution access ·
        member_execution_control_count = 0.
      </p>
    </MemberPageChrome>
  );
}
