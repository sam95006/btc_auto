import { saveLayoutConfig } from "../api_client.js?v=20260503a";
import { applySavedPanelLayout, getPanelTargets, getRuntimeLayout, setRuntimeLayout } from "../layout_state.js?v=20260503a";

let isEditMode = false;
let currentDragged = null;
let currentResized = null;
let startX = 0;
let startY = 0;
let startLeft = 0;
let startTop = 0;
let startWidth = 0;
let startHeight = 0;

const HOTSPOT_SELECTOR = ".scene-hotspot-block, .station-hotspot-btn";
const DRAGGABLE_SELECTOR = [
  "#top-status-bar",
  "#meeting-log-panel",
  "#alert-panel",
  "#chat-dock",
  "#meeting-dock",
  "#scene-modal .scene-stage-frame",
  "#sub-modal-overlay .sub-modal-window",
  "#global-active-modal .global-modal-window",
].join(", ");

export function getIsEditMode() {
  return isEditMode;
}

export function initHotspotEditor() {
  if (document.getElementById("hotspot-editor-toggle")) return;

  const button = document.createElement("button");
  button.id = "hotspot-editor-toggle";
  button.type = "button";
  button.innerText = "Edit Layout";
  button.style.cssText = [
    "position:fixed",
    "bottom:20px",
    "right:20px",
    "z-index:2147483647",
    "background:rgba(79,216,255,0.22)",
    "color:#eefaff",
    "border:1px solid rgba(79,216,255,0.65)",
    "padding:10px 18px",
    "border-radius:999px",
    "cursor:pointer",
    "font-weight:700",
    "backdrop-filter:blur(10px)",
  ].join(";");
  button.onclick = toggleEditMode;
  document.body.appendChild(button);

  document.addEventListener("mousedown", handleMouseDown, true);
  document.addEventListener("mousemove", handleMouseMove);
  document.addEventListener("mouseup", handleMouseUp);
  document.addEventListener("keydown", (event) => {
    if (event.ctrlKey && event.key.toLowerCase() === "e") {
      event.preventDefault();
      toggleEditMode();
    }
  });
}

function toggleEditMode() {
  isEditMode = !isEditMode;
  document.body.classList.toggle("hotspot-edit-mode", isEditMode);

  const button = document.getElementById("hotspot-editor-toggle");
  if (button) {
    button.innerText = isEditMode ? "Exit Layout Edit" : "Edit Layout";
  }

  syncResizeHandles();

  if (isEditMode) {
    injectEditorUI();
  } else {
    removeEditorUI();
  }
}

function syncResizeHandles() {
  document.querySelectorAll(DRAGGABLE_SELECTOR).forEach((element) => {
    if (isEditMode) {
      if (!element.querySelector(":scope > .hs-resize-handle")) {
        const handle = document.createElement("div");
        handle.className = "hs-resize-handle";
        element.appendChild(handle);
      }
    } else {
      element.querySelector(":scope > .hs-resize-handle")?.remove();
    }
  });
}

function injectEditorUI() {
  if (document.getElementById("hotspot-editor-ui")) return;

  const ui = document.createElement("div");
  ui.id = "hotspot-editor-ui";
  ui.innerHTML = `
    <div class="hotspot-editor-toolbar">
      <div class="hotspot-editor-copy">
        <strong>Layout Edit Mode</strong>
        <span>Drag objects and resize from the lower-right corner. Save when you are done.</span>
      </div>
      <button id="hs-save-btn" type="button">Save Layout</button>
      <button id="hs-copy-btn" type="button">Copy JSON</button>
      <button id="hs-close-btn" type="button">Close</button>
    </div>
  `;
  document.body.appendChild(ui);

  const style = document.createElement("style");
  style.id = "hotspot-editor-style";
  style.textContent = `
    .hotspot-editor-toolbar {
      position: fixed;
      top: 12px;
      left: 50%;
      transform: translateX(-50%);
      z-index: 2147483647;
      display: flex;
      gap: 12px;
      align-items: center;
      padding: 12px 16px;
      border-radius: 16px;
      background: rgba(7, 18, 34, 0.92);
      border: 1px solid rgba(79, 216, 255, 0.4);
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.45);
      backdrop-filter: blur(16px);
    }
    .hotspot-editor-copy {
      display: flex;
      flex-direction: column;
      gap: 4px;
      min-width: 320px;
    }
    .hotspot-editor-copy strong {
      color: #eefaff;
      font-size: 14px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .hotspot-editor-copy span {
      color: rgba(238, 250, 255, 0.72);
      font-size: 12px;
    }
    .hotspot-editor-toolbar button {
      border: 1px solid rgba(79, 216, 255, 0.4);
      background: rgba(79, 216, 255, 0.12);
      color: #eefaff;
      border-radius: 10px;
      padding: 8px 14px;
      cursor: pointer;
      font-weight: 700;
    }
    .hotspot-editor-toolbar button:hover {
      background: rgba(79, 216, 255, 0.2);
    }
    .hotspot-edit-mode ${HOTSPOT_SELECTOR} {
      border: 2px dashed rgba(255, 59, 92, 0.92) !important;
      background: rgba(255, 59, 92, 0.18) !important;
      cursor: move !important;
      pointer-events: auto !important;
      opacity: 1 !important;
      z-index: 1000 !important;
    }
    .hotspot-edit-mode ${HOTSPOT_SELECTOR}::after {
      content: "";
      position: absolute;
      right: 0;
      bottom: 0;
      width: 18px;
      height: 18px;
      background: rgba(255, 59, 92, 0.95);
      clip-path: polygon(100% 0, 100% 100%, 0 100%);
      cursor: nwse-resize;
    }
    .hotspot-edit-mode ${DRAGGABLE_SELECTOR} {
      border: 2px dashed rgba(79, 216, 255, 0.95) !important;
      z-index: 10000 !important;
    }
    .hotspot-edit-mode .hs-resize-handle {
      position: absolute;
      right: 0;
      bottom: 0;
      width: 24px;
      height: 24px;
      background: rgba(79, 216, 255, 0.95);
      clip-path: polygon(100% 0, 100% 100%, 0 100%);
      cursor: nwse-resize;
      z-index: 10001;
    }
  `;
  document.head.appendChild(style);

  document.getElementById("hs-close-btn").onclick = toggleEditMode;
  document.getElementById("hs-copy-btn").onclick = copyLayoutJson;
  document.getElementById("hs-save-btn").onclick = saveCurrentLayout;
}

function removeEditorUI() {
  document.getElementById("hotspot-editor-ui")?.remove();
  document.getElementById("hotspot-editor-style")?.remove();
}

function handleMouseDown(event) {
  if (!isEditMode) return;

  const hotspot = event.target.closest(HOTSPOT_SELECTOR);
  if (hotspot) {
    event.preventDefault();
    event.stopPropagation();

    const rect = hotspot.getBoundingClientRect();
    const isResizing = event.clientX > rect.right - 24 && event.clientY > rect.bottom - 24;

    startX = event.clientX;
    startY = event.clientY;
    startLeft = hotspot.offsetLeft;
    startTop = hotspot.offsetTop;
    startWidth = hotspot.offsetWidth;
    startHeight = hotspot.offsetHeight;

    const parentRect = hotspot.parentElement.getBoundingClientRect();
    if (isResizing) {
      currentResized = { el: hotspot, parentRect, mode: "percent" };
    } else {
      currentDragged = { el: hotspot, parentRect, mode: "percent" };
    }
    return;
  }

  const target = event.target.closest(DRAGGABLE_SELECTOR);
  if (!target) return;

  const rect = target.getBoundingClientRect();
  const isResizing = event.clientX > rect.right - 28 && event.clientY > rect.bottom - 28;

  event.preventDefault();
  event.stopPropagation();

  startX = event.clientX;
  startY = event.clientY;
  startWidth = rect.width;
  startHeight = rect.height;
  startLeft = rect.left;
  startTop = rect.top;

  if (window.getComputedStyle(target).position !== "fixed" && window.getComputedStyle(target).position !== "absolute") {
    target.style.position = "fixed";
    target.style.left = `${rect.left}px`;
    target.style.top = `${rect.top}px`;
    target.style.margin = "0";
    target.style.right = "auto";
    target.style.bottom = "auto";
    if (!target.matches("#top-status-bar")) {
      target.style.transform = "none";
    }
  }

  if (isResizing) {
    currentResized = { el: target, mode: "absolute" };
  } else {
    currentDragged = { el: target, mode: "absolute" };
  }
}

function handleMouseMove(event) {
  if (!isEditMode) return;

  if (currentDragged) {
    const dx = event.clientX - startX;
    const dy = event.clientY - startY;

    if (currentDragged.mode === "absolute") {
      currentDragged.el.style.left = `${startLeft + dx}px`;
      currentDragged.el.style.top = `${startTop + dy}px`;
    } else {
      const width = currentDragged.parentRect.width || 1;
      const height = currentDragged.parentRect.height || 1;
      currentDragged.el.style.left = `${((startLeft + dx) / width) * 100}%`;
      currentDragged.el.style.top = `${((startTop + dy) / height) * 100}%`;
    }
  }

  if (currentResized) {
    const dx = event.clientX - startX;
    const dy = event.clientY - startY;

    if (currentResized.mode === "absolute") {
      currentResized.el.style.width = `${Math.max(120, startWidth + dx)}px`;
      currentResized.el.style.height = `${Math.max(80, startHeight + dy)}px`;
    } else {
      const width = currentResized.parentRect.width || 1;
      const height = currentResized.parentRect.height || 1;
      currentResized.el.style.width = `${((startWidth + dx) / width) * 100}%`;
      currentResized.el.style.height = `${((startHeight + dy) / height) * 100}%`;
    }
  }
}

function handleMouseUp() {
  currentDragged = null;
  currentResized = null;
}

function captureHotspots() {
  const grouped = { ...(getRuntimeLayout().hotspots || {}) };

  document.querySelectorAll(HOTSPOT_SELECTOR).forEach((element) => {
    const parent = element.parentElement;
    if (!parent) return;

    const page = element.dataset.layoutPage || element.dataset.page || "MAIN";
    const id = element.dataset.hotspotId || element.dataset.openPage || element.dataset.subModal;
    if (!id) return;

    const label = element.dataset.subLabel || element.querySelector("span")?.innerText || id;
    const section = element.dataset.subModal || null;
    const parentWidth = parent.offsetWidth || 1;
    const parentHeight = parent.offsetHeight || 1;

    const item = {
      id,
      label,
      x: Number((element.offsetLeft / parentWidth).toFixed(3)),
      y: Number((element.offsetTop / parentHeight).toFixed(3)),
      w: Number((element.offsetWidth / parentWidth).toFixed(3)),
      h: Number((element.offsetHeight / parentHeight).toFixed(3)),
    };

    if (section) item.section = section;
    if (!grouped[page]) grouped[page] = [];

    const index = grouped[page].findIndex((entry) => entry.id === id);
    if (index >= 0) {
      grouped[page][index] = item;
    } else {
      grouped[page].push(item);
    }
  });

  return grouped;
}

function capturePanels() {
  const grouped = { ...(getRuntimeLayout().panels || {}) };

  getPanelTargets().forEach(({ key, selector }) => {
    const element = document.querySelector(selector);
    if (!element) return;

    grouped[key] = {
      position: element.style.position || window.getComputedStyle(element).position,
      left: element.style.left || "",
      top: element.style.top || "",
      right: element.style.right || "",
      bottom: element.style.bottom || "",
      width: element.style.width || "",
      height: element.style.height || "",
      transform: element.style.transform || "",
      margin: element.style.margin || "",
    };
  });

  return grouped;
}

function buildLayoutPayload() {
  const current = getRuntimeLayout();
  return {
    version: Number(current.version || 1),
    hotspots: captureHotspots(),
    panels: capturePanels(),
  };
}

async function saveCurrentLayout() {
  const button = document.getElementById("hs-save-btn");
  if (button) button.disabled = true;

  try {
    const layout = buildLayoutPayload();
    const saved = await saveLayoutConfig(layout);
    setRuntimeLayout(saved);
    applySavedPanelLayout(document);
    window.alert("Layout saved. Your positions will stay after reload.");
  } catch (error) {
    window.alert(`Layout save failed: ${error?.message || String(error)}`);
  } finally {
    if (button) button.disabled = false;
  }
}

async function copyLayoutJson() {
  const json = JSON.stringify(buildLayoutPayload(), null, 2);
  try {
    await navigator.clipboard.writeText(json);
    window.alert("Layout JSON copied.");
  } catch (error) {
    console.log(json);
    window.alert("Copy failed. Open DevTools console to read the JSON.");
  }
}
