const PANEL_TARGETS = [
  { key: "topHud", selector: "#top-status-bar" },
  { key: "leftPanel", selector: "#meeting-log-panel" },
  { key: "alertPanel", selector: "#alert-panel" },
  { key: "bottomPanel", selector: "#chat-dock" },
  { key: "rightPanel", selector: "#meeting-dock" },
  { key: "pageModal", selector: "#scene-modal" },
  { key: "pageModalFrame", selector: "#scene-modal .scene-stage-frame" },
  { key: "subModalWindow", selector: "#sub-modal-overlay .sub-modal-window" },
  { key: "globalModalWindow", selector: "#global-active-modal .global-modal-window" },
];

let runtimeLayout = normalizeLayout(window.__NEXUS_LAYOUT__);
window.__NEXUS_LAYOUT__ = runtimeLayout;

function normalizeLayout(payload) {
  const layout = payload && typeof payload === "object" ? payload : {};
  return {
    version: Number(layout.version || 1),
    hotspots: layout.hotspots && typeof layout.hotspots === "object" ? layout.hotspots : {},
    panels: layout.panels && typeof layout.panels === "object" ? layout.panels : {},
  };
}

function normalizeHotspot(defaultHotspot, savedHotspot) {
  const merged = { ...defaultHotspot, ...(savedHotspot || {}) };
  return {
    ...merged,
    x: Number(merged.x ?? defaultHotspot.x ?? 0),
    y: Number(merged.y ?? defaultHotspot.y ?? 0),
    w: Number(merged.w ?? defaultHotspot.w ?? 0.1),
    h: Number(merged.h ?? defaultHotspot.h ?? 0.1),
  };
}

export function setRuntimeLayout(payload) {
  runtimeLayout = normalizeLayout(payload);
  window.__NEXUS_LAYOUT__ = runtimeLayout;
  return runtimeLayout;
}

export function getRuntimeLayout() {
  return runtimeLayout;
}

export function getLayoutHotspots(page, defaults = []) {
  const savedItems = runtimeLayout.hotspots?.[page];
  if (!Array.isArray(savedItems) || !savedItems.length) {
    return defaults;
  }
  const savedById = new Map(savedItems.map((item) => [item.id, item]));
  return defaults.map((item) => normalizeHotspot(item, savedById.get(item.id)));
}

export function getPanelTargets() {
  return PANEL_TARGETS.slice();
}

function hasMeaningfulPanelLayout(saved) {
  if (!saved || typeof saved !== "object") return false;
  return ["left", "top", "right", "bottom", "width", "height"].some(
    (key) => String(saved[key] || "").trim(),
  );
}

export function resetPanelLayout(root = document) {
  PANEL_TARGETS.forEach(({ selector }) => {
    const element = root.querySelector(selector);
    if (!element) return;
    element.style.position = "";
    element.style.left = "";
    element.style.top = "";
    element.style.right = "";
    element.style.bottom = "";
    element.style.width = "";
    element.style.height = "";
    element.style.transform = "";
    element.style.margin = "";
  });
}

export function applySavedPanelLayout(root = document) {
  const panelLayout = runtimeLayout.panels || {};
  PANEL_TARGETS.forEach(({ key, selector }) => {
    const element = root.querySelector(selector);
    const saved = panelLayout[key];
    if (!element || !saved || typeof saved !== "object") return;
    if (!hasMeaningfulPanelLayout(saved)) return;
    if (saved.position) element.style.position = saved.position;
    if (saved.left) element.style.left = saved.left;
    if (saved.top) element.style.top = saved.top;
    if (saved.right) element.style.right = saved.right;
    if (saved.bottom) element.style.bottom = saved.bottom;
    if (saved.width) element.style.width = saved.width;
    if (saved.height) element.style.height = saved.height;
    if (saved.transform !== undefined) element.style.transform = saved.transform;
    if (saved.margin !== undefined) element.style.margin = saved.margin;
  });
}
