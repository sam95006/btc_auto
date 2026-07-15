/**
 * Static Evidence share presets / workspace pins (MVP-19).
 * URL-only navigation · READ ONLY · NOT INVESTMENT ADVICE · no backend · no /data · no secrets
 */

export type EvidencePreset = {
  id: string;
  title: string;
  description: string;
  query: string;
  hash: string;
  category: string;
  gateStatus: string;
  tags: string[];
  targetPage: string;
  operatorUseCase: string;
  safetyNote: string;
  pinTone: "wait" | "blocked" | "pass" | "hold";
  pinStatusLabel: string;
};

export const EVIDENCE_PRESETS: EvidencePreset[] = [
  {
    id: "eth-watch-gate",
    title: "ETH Watch Gate View",
    description: "Unresolved ETH gate excerpts — watch conditions not reappeared.",
    query: "q=ETH&category=backend-gate&unresolved=true",
    hash: "#eth-watch-reappearance",
    category: "backend-gate",
    gateStatus: "WAIT",
    tags: ["ETH", "HOLD", "no 60m"],
    targetPage: "/evidence",
    operatorUseCase: "Daily check: is ETH watch gate still closed?",
    safetyNote: "Wait only · no Run 30m/60m · Stage 4.19 blocked · READ ONLY",
    pinTone: "wait",
    pinStatusLabel: "waiting",
  },
  {
    id: "stage-419-blocker",
    title: "Stage 4.19 Blocker View",
    description: "Why Stage 4.19 remains blocked — dossier checklist + related evidence.",
    query: "q=Stage%204.19&gateStatus=BLOCKED&unresolved=true",
    hash: "#stage-419-dossier",
    category: "backend-gate",
    gateStatus: "BLOCKED",
    tags: ["Stage 4.19", "HOLD"],
    targetPage: "/overview",
    operatorUseCase: "Confirm dossier remains closed under HOLD.",
    safetyNote: "No Stage 4.19 start · documentation / gate only · NOT INVESTMENT ADVICE",
    pinTone: "blocked",
    pinStatusLabel: "blocked",
  },
  {
    id: "safety-invariants",
    title: "Safety Invariants View",
    description: "No order / ARM / production / billing · release safety posture.",
    query: "q=safety&category=safety",
    hash: "#checklist-safety-invariants",
    category: "safety",
    gateStatus: "PASS",
    tags: ["safety", "read-only", "HOLD"],
    targetPage: "/risk-evidence",
    operatorUseCase: "Quick audit of safety invariants under HOLD.",
    safetyNote: "Display only · no control toggles · READ ONLY",
    pinTone: "pass",
    pinStatusLabel: "pass",
  },
  {
    id: "provider-routing",
    title: "Provider Routing View",
    description: "Groq vs Cerebras history · Cerebras-first experiment-only posture.",
    query: "q=provider&category=routing",
    hash: "#btc-cerebras-first",
    category: "routing",
    gateStatus: "HOLD",
    tags: ["routing", "BTC", "HOLD"],
    targetPage: "/provider-shadow",
    operatorUseCase: "Review provider experiment history without opening an editor.",
    safetyNote: "No routing editor · permanent routing=false · Stage 4.19 blocked",
    pinTone: "hold",
    pinStatusLabel: "experiment-only",
  },
  {
    id: "p2h-release-checkpoint",
    title: "P2H Release Checkpoint View",
    description: "HOLD release checkpoint + related release docs.",
    query: "q=P2H&category=release-checkpoint",
    hash: "#p2h-rel",
    category: "release-checkpoint",
    gateStatus: "HOLD",
    tags: ["release checkpoint", "P2H", "HOLD"],
    targetPage: "/evidence",
    operatorUseCase: "Open the archived P2H HOLD checkpoint pack.",
    safetyNote: "Docs archive · no runtime · READ ONLY · NOT INVESTMENT ADVICE",
    pinTone: "hold",
    pinStatusLabel: "HOLD",
  },
  {
    id: "prompt-repair-history",
    title: "Prompt Repair History View",
    description: "P2D prompt repair chain and related excerpts.",
    query: "q=prompt%20repair&category=prompt-repair",
    hash: "#p2d-prompt-repair",
    category: "prompt-repair",
    gateStatus: "PASS",
    tags: ["prompt repair", "ETH"],
    targetPage: "/evidence",
    operatorUseCase: "Trace prompt repair evidence without blind-running soaks.",
    safetyNote: "No MAE/RG edits from UI · wait for ETH watch · Stage 4.19 blocked",
    pinTone: "pass",
    pinStatusLabel: "history",
  },
];

/** Overview pinned workspace shortcuts (subset). */
export const WORKSPACE_PIN_IDS = [
  "eth-watch-gate",
  "stage-419-blocker",
  "safety-invariants",
  "provider-routing",
] as const;

export function getEvidencePreset(id: string): EvidencePreset | undefined {
  return EVIDENCE_PRESETS.find((p) => p.id === id);
}

export function getWorkspacePins(): EvidencePreset[] {
  return WORKSPACE_PIN_IDS.map((id) => getEvidencePreset(id)).filter(
    (p): p is EvidencePreset => Boolean(p),
  );
}

/** Build relative URL for a preset (query + hash navigation only). */
export function presetHref(preset: EvidencePreset): string {
  const q = preset.query ? `?${preset.query}` : "";
  const h = preset.hash.startsWith("#") ? preset.hash : `#${preset.hash}`;
  return `${preset.targetPage}${q}${h}`;
}

/** Absolute share URL when window is available. */
export function presetAbsoluteHref(preset: EvidencePreset, origin?: string): string {
  const rel = presetHref(preset);
  if (origin) return `${origin}${rel}`;
  if (typeof window !== "undefined") return `${window.location.origin}${rel}`;
  return rel;
}
