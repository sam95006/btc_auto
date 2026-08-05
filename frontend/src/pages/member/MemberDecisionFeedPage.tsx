import { MemberPageChrome, EmptyState } from "../../member/MemberPageChrome";
import { LiveSlotStrip, usePageSlots } from "../../member/LiveSlotStrip";

export function MemberDecisionFeedPage() {
  if (decisions.length === 0) {
    return (
      <MemberPageChrome
        titleKey="pages.decisions.title"
        subtitleKey="pages.decisions.emptySubtitle"
      >
        <EmptyState label="No Decisions in DEMO catalog" />
      </MemberPageChrome>
    );
  }


  return (
    <MemberPageChrome
      titleKey="pages.decisions.title"
      subtitleKey="pages.decisions.subtitle"
    >
      {loading ? <p className="muted">Loading live bindings...</p> : null}
      <LiveSlotStrip bindings={items} />
      <EmptyState label="Decision Object list UNAVAILABLE - no synthetic live rows" />
    </MemberPageChrome>
  );
}
