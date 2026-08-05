import { LIFECYCLE_HINT, type LifecycleState } from "./lifecycleStates";

export function IntelligenceStateChip({
  state,
  showHint = false,
}: {
  state: LifecycleState | string;
  showHint?: boolean;
}) {
  const hint =
    state in LIFECYCLE_HINT
      ? LIFECYCLE_HINT[state as LifecycleState]
      : "Unknown state";
  const cls = `member-intel-chip member-intel-${String(state).toLowerCase()}`;
  return (
    <span className={cls} data-lifecycle={state} title={hint}>
      <span className="member-intel-chip-label">{state}</span>
      {showHint ? <span className="member-intel-chip-hint">{hint}</span> : null}
    </span>
  );
}
