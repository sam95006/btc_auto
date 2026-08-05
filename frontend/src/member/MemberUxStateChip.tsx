import {
  UX_STATE_HINT,
  UX_STATE_LABEL,
  type MemberUxState,
} from "./uxStates";

export function MemberUxStateChip({
  state,
  showHint = false,
}: {
  state: MemberUxState;
  showHint?: boolean;
}) {
  return (
    <span
      className={`member-ux-chip member-ux-${state}`}
      data-ux-state={state}
      title={UX_STATE_HINT[state]}
    >
      <span className="member-ux-chip-label">{UX_STATE_LABEL[state]}</span>
      {showHint ? <span className="member-ux-chip-hint">{UX_STATE_HINT[state]}</span> : null}
    </span>
  );
}
