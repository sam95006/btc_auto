import type { SignalStatus } from "../types/nexus";

export function SignalStatusBadge({ status }: { status: SignalStatus | string }) {
  const cls = String(status).replace(/\s+/g, "_");
  return <span className={`signal-badge ${cls}`}>{status}</span>;
}
