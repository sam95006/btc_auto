import { Link } from "react-router-dom";
import { MemberPageChrome } from "../../member/MemberPageChrome";

export function MemberPrivacyPage() {
  return (
    <MemberPageChrome
      title="Privacy"
      subtitle="Public product privacy posture · staging stub · legal review required before launch"
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
