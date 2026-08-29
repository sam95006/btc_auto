/**
 * FOUNDER / PRIVATE surface (Surface D).
 *
 * This tree is built ONLY into the founder-private build (src/entries/
 * founderMain.tsx + founder.html). It must never be imported by the corporate,
 * personal, or enterprise entrypoints. It contains the Founder private operator,
 * diagnostics, live-ops, and runtime views.
 *
 * No real-money controls are enabled here (MAINNET=false, REAL_MONEY=false,
 * ARM off, auto-trading off) — this stage only isolates the surface.
 */
import { Navigate, Route, Routes } from "react-router-dom";
import { FounderDiagnosticsPage } from "../founder/FounderDiagnosticsPage";
import { FounderLiveOpsPage } from "../founder/FounderLiveOpsPage";
import { FounderOperatorShell } from "../founder/FounderOperatorShell";
import { FounderOperatorPage } from "../founder/FounderOperatorPage";
import { FounderRuntimePage } from "../pages/FounderRuntimePage";

export default function FounderApp() {
  return (
    <Routes>
      <Route path="/founder/operator" element={<FounderOperatorShell />}>
        <Route index element={<FounderOperatorPage />} />
      </Route>
      <Route path="/founder/diagnostics" element={<FounderOperatorShell />}>
        <Route index element={<FounderDiagnosticsPage />} />
      </Route>
      <Route path="/founder/live-ops" element={<FounderOperatorShell />}>
        <Route index element={<FounderLiveOpsPage />} />
      </Route>
      <Route path="/founder/runtime" element={<FounderRuntimePage />} />
      <Route path="/*" element={<Navigate to="/founder/operator" replace />} />
    </Routes>
  );
}
