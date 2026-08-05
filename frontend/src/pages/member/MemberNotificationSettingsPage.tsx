import { MemberPageChrome } from "../../member/MemberPageChrome";
import { NotificationPrefsStub } from "../../components/NotificationPrefsStub";

export function MemberNotificationSettingsPage() {
  return (
    <MemberPageChrome
      title="Notification Settings"
      subtitle="Local browser preferences · digest-first · no spam defaults · no cross-device sync in DEMO"
    >
      <NotificationPrefsStub />
      <section className="member-panel">
        <h2 className="nx-sec-title">Alert classes</h2>
        <ul>
          <li>Thesis Integrity Monitor candidates</li>
          <li>Risk / invalidation condition changes</li>
          <li>Outcome Review reminders</li>
          <li>Freshness / availability notices</li>
        </ul>
        <p className="muted sm">Push remains blocked until real OS/browser permission is granted.</p>
      </section>
    </MemberPageChrome>
  );
}
