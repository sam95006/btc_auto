import { MemberPageChrome } from "../../member/MemberPageChrome";
import { LiveSlotStrip, usePageSlots } from "../../member/LiveSlotStrip";

export function MemberAccountPage() {
  const { loading, items } = usePageSlots([
    ["account.profile_card", "runtime", "Profile runtime"],
    ["account.locale_chip", "freshness", "Locale freshness"],
  ]);

  return (
    <MemberPageChrome title="Account" subtitle="Public identity surface · no wallet exposure">
      {loading ? <p className="muted">Loading live bindings...</p> : null}
      <LiveSlotStrip bindings={items} />
      <p className="muted sm">
        Profile fields UNAVAILABLE until auth realm binds · no synthetic live profile.
      </p>
    </MemberPageChrome>
  );
}
