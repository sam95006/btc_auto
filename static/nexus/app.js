import { startStateStore, subscribe, getState } from "./state_store.js?v=20260503a";
import { fetchLayoutConfig, fetchNexusState } from "./api_client.js?v=20260503a";
import { renderTopStatusBar } from "./components/ui_top_status_bar.js?v=20260521f";
import { renderAlertPanel } from "./components/ui_alert_panel.js?v=20260510a";
import { renderChatDock } from "./components/ui_chat_dock.js?v=20260521c";
import { renderMeetingLogPanel } from "./components/ui_meeting_log_panel.js?v=20260520a";
import { renderMeetingDock } from "./components/ui_meeting_dock.js?v=20260510b";
import { buildMainOverviewPage } from "./scenes/scene_main_hq.js?v=20260510b";
import { buildHqPage, getHqModalContent } from "./scenes/scene_hq_roundtable.js?v=20260521f";
import { buildFleetPage, getFleetModalContent } from "./scenes/scene_fleet_bridge_base.js?v=20260510b";
import { buildRadarPage, getRadarModalContent } from "./scenes/scene_radar_outpost.js?v=20260510b";
import { buildNewsPage, getNewsModalContent } from "./scenes/scene_news_nexus.js?v=20260510b";
import { escapeHtml } from "./utils/presentation.js?v=20260510b";
import { initHotspotEditor, getIsEditMode } from "./components/hotspot_editor.js?v=20260503a";
import { applySavedPanelLayout, setRuntimeLayout } from "./layout_state.js?v=20260503a";

const rootRefs = {
  top: document.getElementById("top-status-bar"),
  main: document.getElementById("main-scene"),
  left: document.getElementById("meeting-log-panel"),
  alert: document.getElementById("alert-panel"),
  bottom: document.getElementById("chat-dock"),
  right: document.getElementById("meeting-dock"),
  modal: document.getElementById("scene-modal"),
  modalBody: document.getElementById("scene-modal-body"),
  closeModal: document.getElementById("close-modal"),
  subModal: document.getElementById("sub-modal-overlay"),
  subModalBody: document.getElementById("sub-modal-body"),
  subModalTitle: document.getElementById("sub-modal-title"),
  closeSubModal: document.getElementById("sub-modal-close"),
};

const homeUiState = {
  activeMeeting: "12:00",
  selectedMeetingSlot: "12:00",
  roundTableMinimized: true,
};

const chatUiState = {
  activeStation: "WORLD",
  minimized: false,
};

const meetingUiState = {
  minimized: false,
};

const modalState = {
  page: null,
  subModal: null,
};

const style = document.createElement("style");
style.textContent = `
  #top-status-bar.top-status-bar {
    display: grid !important;
    grid-template-columns: repeat(5, minmax(0, 1fr)) !important;
    gap: 10px !important;
    padding: 12px 16px !important;
    width: min(calc(100vw - 420px), 1180px) !important;
    max-width: min(calc(100vw - 420px), 1180px) !important;
    background: rgba(5, 16, 30, 0.88) !important;
    border: 1px solid rgba(79, 216, 255, 0.16) !important;
    border-radius: 26px !important;
    box-shadow: 0 16px 38px rgba(0, 0, 0, 0.34) !important;
    overflow: hidden !important;
  }
  #top-status-bar .status-board,
  #top-status-bar .status-primary-grid {
    display: contents !important;
  }
  #top-status-bar .status-card {
    display: flex !important;
    flex-direction: column !important;
    justify-content: center !important;
    min-height: 82px !important;
    padding: 12px 14px !important;
    gap: 6px !important;
    border-radius: 16px !important;
    background: rgba(255,255,255,0.03) !important;
    box-shadow: inset 0 0 0 1px rgba(255,255,255,0.05) !important;
  }
  #top-status-bar .status-card span {
    font-size: 12px !important;
    color: rgba(199, 232, 244, 0.86) !important;
    white-space: nowrap !important;
  }
  #top-status-bar .status-card strong {
    font-size: 22px !important;
    color: #eefaff !important;
    white-space: nowrap !important;
  }
  #top-status-bar .status-card small {
    font-size: 11px !important;
    color: rgba(173, 213, 229, 0.78) !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
  }
  #top-status-bar .status-card.good strong,
  #top-status-bar .status-card.good small {
    color: #2ff7a3 !important;
  }
  #top-status-bar .status-card.bad strong,
  #top-status-bar .status-card.bad small {
    color: #ff6b8f !important;
  }
  #meeting-log-panel.meeting-log-panel {
    position: fixed !important;
    left: 14px !important;
    top: 96px !important;
    width: min(300px, calc(100vw - 28px)) !important;
    max-height: min(34vh, 280px) !important;
    padding: 0 !important;
    z-index: 150 !important;
    pointer-events: auto !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
  }
  #meeting-log-panel .rt-panel {
    display: flex !important;
    flex-direction: column !important;
    max-height: min(34vh, 280px) !important;
    border-radius: 14px !important;
    border: 1px solid rgba(79, 216, 255, 0.22) !important;
    background: linear-gradient(180deg, rgba(6, 16, 30, 0.94), rgba(4, 10, 20, 0.88)) !important;
    backdrop-filter: blur(14px) !important;
    overflow: hidden !important;
  }
  #meeting-log-panel .rt-header {
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    padding: 10px 12px 8px !important;
    border-bottom: 1px solid rgba(255,255,255,0.08) !important;
    position: relative !important;
    z-index: 2 !important;
  }
  #meeting-log-panel .rt-kicker { font-size: 10px !important; color: rgba(143,232,255,0.72) !important; letter-spacing: 0.14em !important; }
  #meeting-log-panel .rt-header strong { font-size: 15px !important; color: #eefaff !important; }
  #meeting-log-panel .rt-btn {
    min-width: 52px !important; height: 28px !important; border-radius: 8px !important;
    border: 1px solid rgba(79,216,255,0.28) !important; background: rgba(79,216,255,0.08) !important;
    color: #8fe8ff !important; cursor: pointer !important; font-size: 12px !important;
  }
  #meeting-log-panel .rt-slots {
    display: grid !important; grid-template-columns: repeat(4, 1fr) !important; gap: 6px !important; padding: 8px 10px !important;
  }
  #meeting-log-panel .rt-slot {
    padding: 6px 4px !important; border-radius: 10px !important; border: 1px solid rgba(255,255,255,0.08) !important;
    background: rgba(255,255,255,0.03) !important; color: #dceff5 !important; cursor: pointer !important; text-align: center !important;
  }
  #meeting-log-panel .rt-slot.active { border-color: rgba(79,216,255,0.5) !important; background: rgba(79,216,255,0.14) !important; }
  #meeting-log-panel .rt-slot b { font-size: 12px !important; color: #fff !important; display: block !important; }
  #meeting-log-panel .rt-slot span { font-size: 10px !important; opacity: 0.7 !important; }
  #meeting-log-panel .rt-body { padding: 0 10px 10px !important; overflow-y: auto !important; max-height: calc(min(34vh, 280px) - 118px) !important; }
  #meeting-log-panel .rt-body-title { font-size: 11px !important; color: rgba(173,213,229,0.85) !important; margin: 4px 0 6px !important; }
  #meeting-log-panel .rt-summary p { margin: 0 !important; font-size: 12px !important; line-height: 1.45 !important; color: #eefaff !important; }
  #meeting-log-panel .rt-summary-meta { display: flex !important; gap: 8px !important; margin-bottom: 6px !important; font-size: 10px !important; color: rgba(173,213,229,0.75) !important; }
  #meeting-log-panel .rt-badge { padding: 2px 6px !important; border-radius: 999px !important; background: rgba(79,216,255,0.16) !important; color: #8fe8ff !important; }
  #meeting-log-panel .rt-focus { margin: 8px 0 0 !important; padding-left: 16px !important; font-size: 11px !important; }
  #meeting-log-panel .rt-empty { font-size: 12px !important; color: rgba(173,213,229,0.75) !important; margin: 0 !important; }
  #meeting-log-panel.is-minimized { max-height: none !important; width: auto !important; }
  #meeting-log-panel .rt-fab {
    position: relative !important; width: 72px !important; height: 72px !important; border: none !important;
    background: transparent !important; cursor: pointer !important; padding: 0 !important;
  }
  #meeting-log-panel .rt-fab-ring { position: absolute !important; inset: 0 !important; border-radius: 50% !important; border: 2px solid rgba(79,216,255,0.35) !important; }
  #meeting-log-panel .rt-fab-core { position: absolute !important; inset: 14px !important; border-radius: 50% !important; background: radial-gradient(circle at 30% 30%, #8fe8ff, #123248 70%) !important; }
  #meeting-log-panel .rt-fab-label { position: absolute !important; left: 50% !important; bottom: -2px !important; transform: translateX(-50%) !important; font-size: 11px !important; color: #eefaff !important; }
  #alert-panel.alert-panel {
    right: 18px !important;
    bottom: 18px !important;
    top: auto !important;
    left: auto !important;
    width: 260px !important;
    z-index: 150 !important;
  }
  #meeting-log-panel.is-minimized,
  #meeting-log-panel .rt-fab { pointer-events: auto !important; }
  #meeting-dock.dock-host.meeting-host { display: none !important; }
  #chat-dock.dock-host.chat-host {
    position: fixed !important; left: 14px !important; bottom: 14px !important;
    width: min(520px, calc(100vw - 28px)) !important; z-index: 130 !important; pointer-events: auto !important;
  }
  #chat-dock .game-chat-panel {
    display: flex !important; flex-direction: column !important;
    border-radius: 12px !important; border: 1px solid rgba(0,0,0,0.55) !important;
    border-top: 1px solid rgba(79,216,255,0.2) !important;
    background: linear-gradient(180deg, rgba(4,10,18,0.42), rgba(2,6,12,0.78)) !important;
    backdrop-filter: blur(8px) !important; overflow: hidden !important;
  }
  #chat-dock .game-chat-header { display: flex !important; justify-content: space-between !important; align-items: center !important; padding: 6px 10px !important; background: rgba(0,0,0,0.25) !important; }
  #chat-dock .game-chat-title-kicker { font-size: 9px !important; color: rgba(143,232,255,0.65) !important; letter-spacing: 0.16em !important; }
  #chat-dock .game-chat-title strong { font-size: 13px !important; color: #eefaff !important; }
  #chat-dock .game-chat-hint { font-size: 10px !important; color: rgba(173,213,229,0.7) !important; }
  #chat-dock .game-chat-btn { width: 24px !important; height: 24px !important; border-radius: 6px !important; border: 1px solid rgba(255,255,255,0.12) !important; background: rgba(255,255,255,0.06) !important; color: #cfefff !important; cursor: pointer !important; }
  #chat-dock .game-chat-channels { display: flex !important; flex-wrap: wrap !important; gap: 4px !important; padding: 4px 8px 6px !important; background: rgba(0,0,0,0.2) !important; }
  #chat-dock .game-chat-channel { padding: 3px 8px !important; border-radius: 6px !important; border: 1px solid transparent !important; background: rgba(255,255,255,0.04) !important; color: rgba(200,230,245,0.75) !important; font-size: 11px !important; cursor: pointer !important; }
  #chat-dock .game-chat-channel.active { border-color: rgba(79,216,255,0.45) !important; background: rgba(79,216,255,0.16) !important; color: #fff !important; }
  #chat-dock .game-chat-log { min-height: 88px !important; max-height: min(22vh, 168px) !important; overflow-y: auto !important; padding: 6px 10px !important; font-size: 12px !important; }
  #chat-dock .game-chat-line { display: grid !important; grid-template-columns: 42px max-content 1fr !important; gap: 6px 8px !important; padding: 2px 0 !important; text-shadow: 0 1px 2px rgba(0,0,0,0.85) !important; }
  #chat-dock .game-chat-time { font-size: 10px !important; color: rgba(173,213,229,0.55) !important; }
  #chat-dock .game-chat-speaker { font-weight: 700 !important; font-size: 11px !important; white-space: nowrap !important; }
  #chat-dock .game-chat-speaker--hq { color: #8fe8ff !important; }
  #chat-dock .game-chat-speaker--btc { color: #ffd06b !important; }
  #chat-dock .game-chat-speaker--eth { color: #c8a8ff !important; }
  #chat-dock .game-chat-speaker--sol { color: #7dffb2 !important; }
  #chat-dock .game-chat-speaker--pepe { color: #9fff6d !important; }
  #chat-dock .game-chat-speaker--radar { color: #7de8ff !important; }
  #chat-dock .game-chat-speaker--news { color: #ffb8e8 !important; }
  #chat-dock .game-chat-speaker--risk { color: #ff8f9d !important; }
  #chat-dock .game-chat-speaker--player { color: #7dffb2 !important; }
  #chat-dock .game-chat-msg { color: rgba(238,250,255,0.92) !important; word-break: break-word !important; }
  #chat-dock .game-chat-line--player .game-chat-msg { color: #b8ffd8 !important; }
  #chat-dock .game-chat-empty { margin: 0 !important; font-size: 11px !important; color: rgba(173,213,229,0.65) !important; }
  #chat-dock .game-chat-compose { display: flex !important; gap: 6px !important; padding: 6px 8px !important; background: rgba(0,0,0,0.32) !important; }
  #chat-dock .game-chat-input { flex: 1 !important; border: 1px solid rgba(79,216,255,0.22) !important; border-radius: 8px !important; background: rgba(0,0,0,0.35) !important; color: #eefaff !important; font-size: 12px !important; padding: 6px 10px !important; }
  #chat-dock .game-chat-send { border: 1px solid rgba(79,216,255,0.35) !important; border-radius: 8px !important; background: rgba(79,216,255,0.18) !important; color: #eefaff !important; font-size: 12px !important; padding: 6px 12px !important; cursor: pointer !important; }
  #chat-dock .game-chat-footer { display: flex !important; gap: 6px !important; padding: 4px 10px 6px !important; font-size: 10px !important; color: rgba(173,213,229,0.6) !important; border-top: 1px solid rgba(255,255,255,0.06) !important; }
  #chat-dock .game-chat-footer-tag { color: rgba(143,232,255,0.85) !important; font-weight: 700 !important; }
  #chat-dock .game-chat-fab { position: relative !important; width: 64px !important; height: 64px !important; border: none !important; background: transparent !important; cursor: pointer !important; }
  #chat-dock .game-chat-fab-ring { position: absolute !important; inset: 0 !important; border-radius: 50% !important; border: 2px solid rgba(79,216,255,0.35) !important; }
  #chat-dock .game-chat-fab-core { position: absolute !important; inset: 12px !important; border-radius: 50% !important; background: radial-gradient(circle at 30% 30%, #7dffb2, #123248 72%) !important; }
  #chat-dock .game-chat-fab-label { position: absolute !important; left: 50% !important; bottom: -4px !important; transform: translateX(-50%) !important; font-size: 10px !important; color: #eefaff !important; white-space: nowrap !important; }
  #chat-dock .chat-dock.is-minimized { width: auto !important; background: transparent !important; }
  #top-status-bar {
    z-index: 140 !important;
  }
  #scene-modal.scene-modal.open {
    display: block !important;
  }
  .boot-error {
    position: fixed;
    left: 20px;
    right: 20px;
    bottom: 20px;
    z-index: 99999;
    padding: 10px 14px;
    border-radius: 12px;
    background: rgba(80, 8, 20, 0.95);
    color: #fff;
    border: 1px solid rgba(255, 90, 120, 0.5);
    font-size: 12px;
    line-height: 1.5;
  }
`;
document.head.appendChild(style);

function clearBootErrors() {
  document.querySelectorAll(".boot-error").forEach((node) => node.remove());
}

function showError(message) {
  clearBootErrors();
  document.body.insertAdjacentHTML("beforeend", `<div class="boot-error">${escapeHtml(message)}</div>`);
}

function updateChatUiState(patch) {
  Object.assign(chatUiState, patch);
  renderApp(getState());
}

function updateMeetingUiState(patch) {
  if (Object.prototype.hasOwnProperty.call(patch, "activeMeeting")) {
    homeUiState.activeMeeting = patch.activeMeeting;
    homeUiState.selectedMeetingSlot = patch.activeMeeting;
  }
  if (Object.prototype.hasOwnProperty.call(patch, "selectedSlot")) {
    homeUiState.selectedMeetingSlot = patch.selectedSlot;
    homeUiState.activeMeeting = patch.selectedSlot;
  }
  if (Object.prototype.hasOwnProperty.call(patch, "selectedMeetingSlot")) {
    homeUiState.selectedMeetingSlot = patch.selectedMeetingSlot;
    homeUiState.activeMeeting = patch.selectedMeetingSlot;
  }
  if (Object.prototype.hasOwnProperty.call(patch, "roundTableMinimized")) {
    homeUiState.roundTableMinimized = patch.roundTableMinimized;
  }
  renderApp(getState());
}

function closeModal() {
  modalState.page = null;
  closeSubModal();
  if (rootRefs.modal) rootRefs.modal.classList.remove("open");
  if (rootRefs.modalBody) rootRefs.modalBody.innerHTML = "";
}

function openPage(page) {
  if (!page || page === "MAIN") {
    closeModal();
    return;
  }
  modalState.page = page;
  renderApp(getState());
}

function closeSubModal() {
  modalState.subModal = null;
  if (rootRefs.subModal) rootRefs.subModal.classList.remove("open");
  if (rootRefs.subModalBody) rootRefs.subModalBody.innerHTML = "";
  if (rootRefs.subModalTitle) rootRefs.subModalTitle.textContent = "詳細資訊";
}

function openSubModal(page, section, label = "") {
  if (!page || !section) return;
  modalState.subModal = { page, section, label };
  renderSubModal(getState());
}

function getPageConfig(page, state) {
  if (!page || page === "MAIN") return buildMainOverviewPage(state, homeUiState);
  if (page === "HQ") return buildHqPage(state);
  if (page === "RADAR") return buildRadarPage(state);
  if (page === "NEWS") return buildNewsPage(state);
  return buildFleetPage(page, state);
}

function bindOpenPageHandlers(scope) {
  scope.querySelectorAll("[data-open-page]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const page = button.dataset.openPage;
      const meetingSlot = button.dataset.meetingSlot;
      if (meetingSlot) {
        homeUiState.selectedMeetingSlot = meetingSlot;
      }
      openPage(page);
    });
  });

  scope.querySelectorAll("[data-sub-modal]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      openSubModal(button.dataset.page, button.dataset.subModal, button.dataset.subLabel || "");
    });
  });
}

function handleDelegatedClick(event) {
  const subModalButton = event.target.closest("[data-sub-modal]");
  if (subModalButton) {
    event.preventDefault();
    event.stopPropagation();
    openSubModal(subModalButton.dataset.page, subModalButton.dataset.subModal, subModalButton.dataset.subLabel || "");
    return;
  }

  const pageButton = event.target.closest("[data-open-page]");
  if (pageButton) {
    event.preventDefault();
    event.stopPropagation();
    const page = pageButton.dataset.openPage;
    const meetingSlot = pageButton.dataset.meetingSlot;
    if (meetingSlot) {
      homeUiState.selectedMeetingSlot = meetingSlot;
    }
    openPage(page);
    return;
  }

  const meetingSlotButton = event.target.closest("[data-meeting-slot]");
  if (meetingSlotButton) {
    event.preventDefault();
    event.stopPropagation();
    const slot = meetingSlotButton.dataset.meetingSlot || "00:00";
    homeUiState.activeMeeting = slot;
    homeUiState.selectedMeetingSlot = slot;
    renderApp(getState());
    return;
  }

  const roundtableToggle = event.target.closest("[data-roundtable-toggle]");
  if (roundtableToggle) {
    event.preventDefault();
    event.stopPropagation();
    homeUiState.roundTableMinimized = roundtableToggle.dataset.roundtableAction !== "expand";
    renderApp(getState());
  }
}

function resolveSubModalContent(state, page, section) {
  if (page === "HQ") return getHqModalContent(state, section);
  if (page === "RADAR") return getRadarModalContent(state, section);
  if (page === "NEWS") return getNewsModalContent(state, section);
  if (["BTC", "ETH", "SOL", "PEPE"].includes(page)) return getFleetModalContent(state, page, section);
  return `<p class="panel-empty">目前沒有可顯示的詳細資訊。</p>`;
}

function renderSubModal(state) {
  if (!rootRefs.subModal || !rootRefs.subModalBody || !rootRefs.subModalTitle) return;
  const current = modalState.subModal;
  if (!current) {
    closeSubModal();
    return;
  }
  rootRefs.subModal.classList.add("open");
  rootRefs.subModalTitle.textContent = current.label || current.section || "詳細資訊";
  const content = resolveSubModalContent(state, current.page, current.section);
  rootRefs.subModalBody.innerHTML = content || `<p class="panel-empty">目前沒有可顯示的詳細資訊。</p>`;
}

function renderHomeScene(state) {
  if (!rootRefs.main) return;
  const page = buildMainOverviewPage(state, homeUiState);
  rootRefs.main.innerHTML = `<div class="reference-scene">${page.center}</div>`;
  bindOpenPageHandlers(rootRefs.main);
}

function renderHomeLeft(state) {
  if (!rootRefs.left) return;
  renderMeetingLogPanel(rootRefs.left, state, homeUiState, updateMeetingUiState);
}

function renderHomeRight(state) {
  if (!rootRefs.right) return;
  rootRefs.right.innerHTML = "";
}

function renderModal(state) {
  if (!rootRefs.modal || !rootRefs.modalBody) return;
  if (!modalState.page) {
    closeModal();
    return;
  }

  const page = getPageConfig(modalState.page, state);
  rootRefs.modal.classList.add("open");

  if (page.stationHtml) {
    rootRefs.modalBody.innerHTML = page.stationHtml;
    bindOpenPageHandlers(rootRefs.modalBody);
    return;
  }

  rootRefs.modalBody.innerHTML = `
    <section class="scene-workspace">
      <div class="workspace-grid workspace-grid--modal">
        <section class="workspace-stage-panel">${page.center || ""}</section>
        <aside class="detail-panel-stack right-intel-stack">${page.right || ""}</aside>
      </div>
    </section>
  `;
  bindOpenPageHandlers(rootRefs.modalBody);
  renderSubModal(state);
}

function renderApp(state) {
  if (!state) return;
  try {
    renderTopStatusBar(rootRefs.top, state);
    renderAlertPanel(rootRefs.alert, state);
    renderChatDock(rootRefs.bottom, state, chatUiState, updateChatUiState);
    renderHomeScene(state);
    renderHomeLeft(state);
    renderHomeRight(state);
    renderModal(state);
    renderSubModal(state);
    // Temporarily skip persisted panel layout during UI recovery.
    // Old saved coordinates were pushing working panels off-screen.
    clearBootErrors();
  } catch (error) {
    showError(`UI render failed: ${error?.message || String(error)}`);
  }
}

rootRefs.closeModal?.addEventListener("click", closeModal);
rootRefs.closeSubModal?.addEventListener("click", closeSubModal);
rootRefs.modal?.addEventListener("click", (event) => {
  if (event.target === rootRefs.modal) closeModal();
});
rootRefs.subModal?.addEventListener("click", (event) => {
  if (event.target === rootRefs.subModal) closeSubModal();
});
document.addEventListener("click", handleDelegatedClick, true);

try {
  initHotspotEditor();
} catch (error) {
  showError(`Layout editor init failed: ${error?.message || String(error)}`);
}

subscribe((state) => {
  if (typeof getIsEditMode === "function" && getIsEditMode()) return;
  renderApp(state);
});

startStateStore().catch((error) => {
  showError(`UI bootstrap failed: ${error?.message || String(error)}`);
});

fetchLayoutConfig()
  .then((layout) => {
    setRuntimeLayout(layout);
    if (getState()) renderApp(getState());
  })
  .catch((error) => {
    showError(`Layout bootstrap failed: ${error?.message || String(error)}`);
  });

window.setTimeout(async () => {
  if (getState()) return;
  try {
    const snapshot = await fetchNexusState();
    renderApp({
      ...snapshot,
      transport: {
        connected: true,
        source: "boot-fallback",
      },
    });
  } catch (error) {
    showError(`UI fallback failed: ${error?.message || String(error)}`);
  }
}, 1200);

