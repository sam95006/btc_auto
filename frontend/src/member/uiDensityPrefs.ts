export type UiDensity = "SIMPLE" | "EXPERT";

const KEY = "nexus_ui_density_v1821";

/** Keep legacy viewPrefs (simple/advanced) in sync with SIMPLE/EXPERT. */
function syncLegacyViewMode(d: UiDensity): void {
  try {
    const mode = d === "EXPERT" ? "advanced" : "simple";
    localStorage.setItem("nexus_mi_view_pref_v1", mode);
    window.dispatchEvent(new CustomEvent("nexus-view-mode", { detail: mode }));
  } catch {
    /* ignore */
  }
}

export function loadUiDensity(): UiDensity {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "EXPERT") return "EXPERT";
    if (v === "SIMPLE") return "SIMPLE";
    /* Migrate legacy viewPrefs once */
    const legacy = localStorage.getItem("nexus_mi_view_pref_v1");
    if (legacy === "advanced") return "EXPERT";
  } catch {
    /* ignore */
  }
  return "SIMPLE";
}

export function saveUiDensity(d: UiDensity): void {
  try {
    localStorage.setItem(KEY, d);
  } catch {
    /* ignore */
  }
  syncLegacyViewMode(d);
}

export function densityToViewMode(d: UiDensity): "simple" | "advanced" {
  return d === "EXPERT" ? "advanced" : "simple";
}

export function viewModeToDensity(mode: "simple" | "advanced"): UiDensity {
  return mode === "advanced" ? "EXPERT" : "SIMPLE";
}
