export type UiDensity = "SIMPLE" | "EXPERT";

const KEY = "nexus_ui_density_v1821";

export function loadUiDensity(): UiDensity {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "EXPERT") return "EXPERT";
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
}
