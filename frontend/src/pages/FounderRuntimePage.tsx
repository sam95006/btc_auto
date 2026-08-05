import { Navigate } from "react-router-dom";

/**
 * Legacy /founder/runtime → Founder Private Operator shell.
 * Member sessions hit FounderAuthGate denial; no private panels leak via member nav.
 */
export function FounderRuntimePage() {
  return <Navigate to="/founder/operator" replace />;
}
