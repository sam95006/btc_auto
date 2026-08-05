/** PUB-E Founder Private Operator UI types — Founder-only, never member-bound. */

export type FounderPanelId =
  | "capture"
  | "provider"
  | "decision"
  | "execution_sim"
  | "risk"
  | "ledger"
  | "checkpoint"
  | "reflection"
  | "lesson"
  | "qualification"
  | "storage"
  | "kill_switch";

export type FounderOperatorPanel = {
  id: FounderPanelId | string;
  title: string;
  health: string;
  summary: string;
  metrics: Record<string, unknown>;
  notes: string[];
  readOnly: boolean;
  exchangeWriteEnabled: boolean;
  memberVisible: boolean;
};

export type FounderOperatorSnapshot = {
  schema: string;
  ok: boolean;
  founderOnly: boolean;
  memberAccessible: boolean;
  researchOnly: boolean;
  realExecutionEnabled: boolean;
  armEnabled: boolean;
  exchangeWriteEnabled: boolean;
  generatedAt: string;
  actor: { tier: string; identitySource: string };
  panels: FounderOperatorPanel[];
  panelIds: string[];
  hardBans: string[];
  note: string;
  error?: string;
};

export type FounderStatus = {
  ok: boolean;
  founderOnly?: boolean;
  memberAccessible?: boolean;
  operatorUiEnabled?: boolean;
  tier?: string;
  identitySource?: string;
  realExecutionEnabled?: boolean;
  error?: string;
};

export const FOUNDER_OPERATOR_NAV: { id: FounderPanelId; label: string; hash: string }[] = [
  { id: "capture", label: "Capture", hash: "#capture" },
  { id: "provider", label: "Provider", hash: "#provider" },
  { id: "decision", label: "Decision", hash: "#decision" },
  { id: "execution_sim", label: "Execution Sim", hash: "#execution_sim" },
  { id: "risk", label: "Risk", hash: "#risk" },
  { id: "ledger", label: "Ledger", hash: "#ledger" },
  { id: "checkpoint", label: "Checkpoint", hash: "#checkpoint" },
  { id: "reflection", label: "Reflection", hash: "#reflection" },
  { id: "lesson", label: "Lesson", hash: "#lesson" },
  { id: "qualification", label: "Qualification", hash: "#qualification" },
  { id: "storage", label: "Storage", hash: "#storage" },
  { id: "kill_switch", label: "Kill-Switch", hash: "#kill_switch" },
];
