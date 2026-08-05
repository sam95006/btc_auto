import { MemberPageChrome, EmptyState } from "../../member/MemberPageChrome";
import { LiveSlotStrip, usePageSlots } from "../../member/LiveSlotStrip";

export function MemberEvidencePage() {
  const { loading, items } = usePageSlots([
    ["evidence.list_table", "freshness", "Evidence freshness"],
    ["evidence.summary_card", "availability", "Summary"],
    ["evidence.polarity_chip", "availability", "Polarity"],
    ["evidence.freshness_chip", "freshness", "Freshness chip"],
    ["evidence.polarity_chart", "btc", "Polarity chart"],
  ]);

  return (
    <MemberPageChrome
      titleKey="pages.evidence.title"
      subtitleKey="pages.evidence.subtitle"
    >
      {items.length === 0 ? (
        <EmptyState label="No evidence rows" />
      ) : (
        <ul className="member-list">
          {items.map((e) => (
            <li key={`${e.decisionId}-${e.id}`} className="member-panel">
              <div className="member-card-meta">
                <strong>{e.title}</strong>
                <span className="member-chip">{e.polarity}</span>
              </div>
              <p>{e.summary}</p>
              <p className="muted sm">
                {e.source} · {e.asOf} · {e.freshness} · Decision{" "}
                <DecisionLink id={e.decisionId} />
              </p>
            </li>
          ))}
        </ul>
      )}

    </MemberPageChrome>
  );
}
