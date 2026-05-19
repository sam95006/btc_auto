import { escapeHtml, normalizeText, translateMeetingType } from "../utils/presentation.js?v=20260510a";

function findMeetingBySlot(state, slot) {
  const meetings = Array.isArray(state.meetings) ? state.meetings : [];
  return meetings.find((item) => String(item.time || "").slice(11, 16) === slot) || null;
}

export function renderMeetingDock(root, state, uiState, updateUiState) {
  const minimized = Boolean(uiState.minimized);
  const selectedSlot = uiState.selectedSlot || "00:00";
  const meeting = findMeetingBySlot(state, selectedSlot);
  const conclusion = meeting?.conclusion || {};
  const nextFocus = Array.isArray(conclusion.next_6h_focus) ? conclusion.next_6h_focus : [];
  const forbidden = Object.values(conclusion.forbidden_actions || {}).flat();

  root.innerHTML = `
    <section class="dock-window dock-window--meeting ${minimized ? "is-minimized" : ""}">
      <header class="dock-header">
        <div>
          <span class="dock-label">圓桌固定會議</span>
          <strong>${escapeHtml(selectedSlot)} 會議結果</strong>
        </div>
        <div class="dock-actions">
          <button type="button" class="dock-action" data-meeting-toggle>${minimized ? "展開" : "縮小"}</button>
        </div>
      </header>
      <div class="dock-body">
        <nav class="dock-tabs">
          ${["00:00", "06:00", "12:00", "18:00"]
            .map(
              (slot) => `
                <button type="button" class="dock-tab ${slot === selectedSlot ? "active" : ""}" data-meeting-slot="${slot}">
                  ${slot}
                </button>
              `,
            )
            .join("")}
        </nav>
        <div class="dock-content" data-scroll-key="meeting-dock-${selectedSlot}">
          ${
            meeting
              ? `
                <article class="dock-summary-card">
                  <b>${escapeHtml(translateMeetingType(meeting.type || "SCHEDULED_ROUND_TABLE"))}</b>
                  <p>${escapeHtml(normalizeText(conclusion.summary || meeting.summary, "目前沒有可顯示的會議摘要。"))}</p>
                </article>
                <article class="dock-summary-card">
                  <b>接下來重點</b>
                  <p>${escapeHtml(normalizeText(nextFocus.join(" / "), "目前沒有新的焦點項目。"))}</p>
                </article>
                <article class="dock-summary-card">
                  <b>禁止操作</b>
                  <p>${escapeHtml(normalizeText(forbidden.join(" / "), "目前沒有新的禁止操作。"))}</p>
                </article>
              `
              : `<p class="station-empty">目前沒有該時段的會議內容。</p>`
          }
        </div>
      </div>
    </section>
  `;

  root.querySelector("[data-meeting-toggle]")?.addEventListener("click", () => {
    updateUiState({ minimized: !minimized });
  });

  root.querySelectorAll("[data-meeting-slot]").forEach((button) => {
    button.addEventListener("click", () => {
      updateUiState({ selectedSlot: button.dataset.meetingSlot, minimized: false });
    });
  });
}
