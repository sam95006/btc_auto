import { escapeHtml } from "../utils/presentation.js?v=20260520a";

const FIXED_SLOTS = ["00:00", "06:00", "12:00", "18:00"];

function cleanText(value, fallback = "目前沒有可顯示的會議摘要。") {
  const text = String(value ?? "").trim();
  if (!text) return fallback;
  if (/\?{2,}/.test(text)) return fallback;
  return text;
}

function meetingTypeLabel(type) {
  const key = String(type || "").toUpperCase();
  if (key === "EMERGENCY_ROUND_TABLE") return "緊急圓桌";
  if (key === "SCHEDULED_ROUND_TABLE") return "固定圓桌";
  return "圓桌";
}

function findMeetingBySlot(meetings, slot) {
  const matches = meetings.filter((item) => {
    if (String(item?.slot || "") === slot) return true;
    const time = String(item?.time || "");
    return time.slice(11, 16) === slot || time.includes(` ${slot}:`) || time.startsWith(`${slot}:`);
  });
  if (!matches.length) return null;
  return [...matches].sort((a, b) => String(b.time || "").localeCompare(String(a.time || "")))[0];
}

function findMeetingById(meetings, id) {
  return meetings.find((item) => String(item?.meeting_id || "") === String(id || "")) || null;
}

function resolveActiveMeeting(meetings, activeMeeting) {
  if (!activeMeeting) {
    return findMeetingBySlot(meetings, "12:00") || meetings[0] || null;
  }
  if (String(activeMeeting).includes(":")) {
    return findMeetingBySlot(meetings, activeMeeting) || null;
  }
  return findMeetingById(meetings, activeMeeting) || null;
}

function renderSlotButtons(meetings, activeMeeting) {
  return FIXED_SLOTS.map((slot) => {
    const slotMeeting = findMeetingBySlot(meetings, slot);
    const active = String(activeMeeting) === slot;
    return `
      <button type="button" class="rt-slot ${active ? "active" : ""} ${slotMeeting ? "has-data" : ""}" data-meeting-slot="${slot}" title="${slotMeeting ? "查看結果" : "尚無紀錄"}">
        <b>${slot}</b>
        <span>${slotMeeting ? "✓" : "—"}</span>
      </button>
    `;
  }).join("");
}

function renderResultBlock(meeting, activeMeeting) {
  const label = String(activeMeeting || "12:00");
  if (!meeting) {
    return `<p class="rt-empty">${escapeHtml(label)} 尚無會議紀錄。</p>`;
  }
  const conclusion = meeting?.conclusion || {};
  const summary = cleanText(conclusion.summary || meeting.summary);
  const nextFocus = Array.isArray(conclusion.next_6h_focus)
    ? conclusion.next_6h_focus.map((item) => cleanText(item, "")).filter(Boolean).slice(0, 2)
    : [];
  return `
    <div class="rt-summary">
      <div class="rt-summary-meta">
        <span class="rt-badge">${escapeHtml(meetingTypeLabel(meeting.type))}</span>
        <time>${escapeHtml(meeting.time || "--")}</time>
      </div>
      <p>${escapeHtml(summary)}</p>
      ${nextFocus.length ? `<ul class="rt-focus">${nextFocus.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}
    </div>
  `;
}

export function renderMeetingLogPanel(root, state, uiState, updateUiState) {
  if (!root) return;

  const meetings = Array.isArray(state?.meetings) ? state.meetings : [];
  const activeMeeting = uiState?.activeMeeting || uiState?.selectedMeetingSlot || "12:00";
  const roundTableMinimized = Boolean(uiState?.roundTableMinimized);
  const currentMeeting = resolveActiveMeeting(meetings, activeMeeting);

  if (roundTableMinimized) {
    root.classList.add("is-minimized");
    root.innerHTML = `
      <button type="button" class="rt-fab" data-roundtable-toggle data-roundtable-action="expand" title="展開圓桌會議">
        <span class="rt-fab-ring"></span>
        <span class="rt-fab-core"></span>
        <span class="rt-fab-label">圓桌</span>
      </button>
    `;
    return;
  }

  root.classList.remove("is-minimized");
  root.innerHTML = `
    <section class="rt-panel">
      <header class="rt-header">
        <div>
          <span class="rt-kicker">ROUNDTABLE</span>
          <strong>圓桌會議</strong>
        </div>
        <button type="button" class="rt-btn" data-roundtable-toggle data-roundtable-action="collapse" title="收合">縮小</button>
      </header>
      <div class="rt-slots">${renderSlotButtons(meetings, activeMeeting)}</div>
      <div class="rt-body">
        <div class="rt-body-title">${escapeHtml(currentMeeting?.time?.slice(11, 16) || activeMeeting)} 結果</div>
        ${renderResultBlock(currentMeeting, activeMeeting)}
      </div>
    </section>
  `;
}
