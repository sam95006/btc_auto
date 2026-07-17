/** Simple/Advanced view preference (local only). */

const KEY = "nexus_mi_view_pref_v1";

export type ViewMode = "simple" | "advanced";

export function loadViewMode(): ViewMode {
  try {
    const v = localStorage.getItem(KEY);
    return v === "advanced" ? "advanced" : "simple";
  } catch {
    return "simple";
  }
}

export function saveViewMode(mode: ViewMode) {
  try {
    localStorage.setItem(KEY, mode);
  } catch {
    /* ignore */
  }
}
