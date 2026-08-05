import { MemberPageChrome } from "../../member/MemberPageChrome";
import { LiveSlotStrip, usePageSlots } from "../../member/LiveSlotStrip";

export function MemberPrivacyPage() {
  const { loading, items } = usePageSlots([
    ["privacy.consent_table", "availability", "Consent availability"],
    ["privacy.consent_chip", "qual", "Consent"],
  ]);

  return (
    <MemberPageChrome title="Privacy" subtitle="Consent · export · deletion readiness">
      {loading ? <p className="muted">Loading live bindings...</p> : null}
      <LiveSlotStrip bindings={items} />
      <ul className="muted sm">
        <li>No private Lesson Memory in Member realm</li>
        <li>No exchange credentials stored in this surface</li>
      </ul>
    </MemberPageChrome>
  );
}
