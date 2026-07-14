/** Consistent HOLD / BLOCKED / PASS / READY / WAIT status labels (MVP-13). */

export type StatusTone = "hold" | "blocked" | "pass" | "ready" | "wait" | "neutral";

const TONE_CLASS: Record<StatusTone, string> = {
  hold: "status-badge status-hold",
  blocked: "status-badge status-blocked",
  pass: "status-badge status-pass",
  ready: "status-badge status-ready",
  wait: "status-badge status-wait",
  neutral: "status-badge status-neutral",
};

export function StatusBadge({
  tone,
  children,
}: {
  tone: StatusTone;
  children: string;
}) {
  return <span className={TONE_CLASS[tone]}>{children}</span>;
}
