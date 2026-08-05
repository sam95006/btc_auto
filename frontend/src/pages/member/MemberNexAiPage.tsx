import { MemberPageChrome } from "../../member/MemberPageChrome";
import { LiveSlotStrip, usePageSlots } from "../../member/LiveSlotStrip";

/** NEX AI — PUB2-B live bindings + PUB2-J i18n; no DEMO conversation fabrication. */
export function MemberNexAiPage() {
  const { loading, items } = usePageSlots([
    ["nexai.availability_card", "availability", "NEX AI availability"],
    ["nexai.disclaimer_chip", "qual", "Disclaimer"],
    ["nexai.status_gauge", "runtime", "Status"],
  ]);

  return (
    <MemberPageChrome titleKey="pages.nexAi.title" subtitleKey="pages.nexAi.subtitle">
      {loading ? <p className="muted">Loading live bindings...</p> : null}
      <LiveSlotStrip bindings={items} />
      <section className="member-panel">
        <p className="muted">
          Conversation UNAVAILABLE until live NEX AI gateway is bound. No synthetic live replies.
        </p>
      </section>
    </MemberPageChrome>
  );
}
