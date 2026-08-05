import { MemberPageChrome } from "../../member/MemberPageChrome";
import { LiveSlotStrip, usePageSlots } from "../../member/LiveSlotStrip";

export function MemberPrivacyPage() {
  const { loading, items } = usePageSlots([
    ["privacy.consent_table", "availability", "Consent availability"],
    ["privacy.consent_chip", "qual", "Consent"],
  ]);

  return (
    <MemberPageChrome
      titleKey="pages.privacy.title"
      subtitleKey="pages.privacy.subtitle"
    >
      <section className="member-panel">
        <h2 className="nx-sec-title">What we process (conceptual)</h2>
        <ul>
          <li>Account identifiers in the public identity realm</li>
          <li>Decision Objects you create (Context, Thesis, Evidence, Outcome, Review)</li>
          <li>Notification preferences stored locally in this DEMO shell</li>
        </ul>
      </section>
      <section className="member-panel">
        <h2 className="nx-sec-title">What we never expose here</h2>
        <ul>
          <li>Private Founder strategies, weights, Lesson Memory</li>
          <li>Exchange API keys, orders, positions, wallets</li>
          <li>Custodial control or withdrawal permissions</li>
        </ul>
      </section>
      <p className="muted sm">
        <Link to="/account-deletion">Account Deletion</Link> ·{" "}
        <Link to="/notification-settings">Notification Settings</Link>
      </p>

    </MemberPageChrome>
  );
}
