import { MemberPageChrome } from "../../member/MemberPageChrome";
import { LiveSlotStrip, usePageSlots } from "../../member/LiveSlotStrip";

export function MemberNotificationSettingsPage() {
  const { loading, items } = usePageSlots([
    ["notify.settings_table", "freshness", "Notify freshness"],
    ["notify.decision_chip", "availability", "Decision notify"],
    ["notify.risk_chip", "qual", "Risk notify"],
    ["notify.stale_chip", "freshness", "Stale notify"],
  ]);

  return (
    <MemberPageChrome
      titleKey="pages.notifications.title"
      subtitleKey="pages.notifications.subtitle"

    >
      {loading ? <p className="muted">Loading live bindings...</p> : null}
      <LiveSlotStrip bindings={items} />
      <p className="muted sm">
        Preference persistence UNAVAILABLE until auth binds · no synthetic live prefs.
      </p>
    </MemberPageChrome>
  );
}
