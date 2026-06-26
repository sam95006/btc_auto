import {
  buildRejectNarration,
  buildRoleWindows,
  buildStationConversation,
  escapeHtml,
  getLatestMeeting,
  normalizeText,
  translateMeetingType,
  translateStation,
} from "../utils/presentation.js?v=20260510a";

function renderBulletList(items, emptyText) {
  if (!Array.isArray(items) || !items.length) {
    return `<p class="station-empty">${escapeHtml(emptyText)}</p>`;
  }

  return `<ul class="station-list">${items
    .map((item) => `<li>${escapeHtml(normalizeText(item, emptyText))}</li>`)
    .join("")}</ul>`;
}

export function renderStationOverview(state, station, title) {
  const briefing = state.station_briefings?.[station] || {};
  const latestMeeting = getLatestMeeting(state);
  const stationInstructions = briefing.station_instructions || [];
  const fleetInstructions = briefing.fleet_instructions || [];
  const forbiddenActions = briefing.forbidden_actions || [];
  const watchlist = briefing.watchlist || [];
  const riskNotes = briefing.risk_notes || [];

  return `
    <article class="station-context-card station-context-hero">
      <div class="station-card-header">
        <div>
          <h3>${escapeHtml(title || `${translateStation(station)} 總覽`)}</h3>
          <p class="station-summary">${escapeHtml(
            normalizeText(briefing.summary || latestMeeting?.conclusion?.summary, "目前沒有可顯示的站點摘要。"),
          )}</p>
        </div>
        <div class="meeting-badge">
          <strong>${escapeHtml(translateMeetingType(briefing.meeting_type || latestMeeting?.type || "SCHEDULED_ROUND_TABLE"))}</strong>
          <span>${escapeHtml(briefing.updated_at || latestMeeting?.time || "--")}</span>
        </div>
      </div>
    </article>
    <article class="station-context-card">
      <h3>指令摘要</h3>
      ${renderBulletList([...stationInstructions, ...fleetInstructions], "目前沒有新的行動指令。")}
    </article>
    <article class="station-context-card">
      <h3>禁止操作</h3>
      ${renderBulletList(forbiddenActions, "目前沒有新的禁止操作。")}
    </article>
    <article class="station-context-card">
      <h3>觀察名單</h3>
      ${renderBulletList(watchlist, "目前沒有新的觀察名單。")}
    </article>
    <article class="station-context-card">
      <h3>風險備註</h3>
      ${renderBulletList(riskNotes, "目前沒有新的風險備註。")}
    </article>
  `;
}

export function renderStationChats(state, station) {
  const chats = buildStationConversation(state, station);
  if (!chats.length) {
    return `<p class="station-empty">目前沒有新的通訊內容。</p>`;
  }

  return `
    <div class="station-chat-list" data-scroll-key="station-chat-${station}">
      ${chats
        .map(
          (item) => `
            <article class="station-chat-row station-chat-${String(item.importance || "INFO").toLowerCase()}">
              <header>
                <b>${escapeHtml(item.speaker || "系統")}</b>
                <span>${escapeHtml(item.timestamp || "--")} / ${escapeHtml(item.source || "站內通訊")}</span>
              </header>
              <p>${escapeHtml(normalizeText(item.message, "目前沒有新的通訊內容。"))}</p>
            </article>
          `,
        )
        .join("")}
    </div>
  `;
}

export function renderRejectSummary(state, station) {
  const audits = (state.decision_audit || []).filter((item) => {
    const symbol = String(item.symbol || "").toUpperCase();
    if (station === "HQ" || station === "RISK") return item.approved === false;
    return item.approved === false && symbol.includes(station);
  });

  if (!audits.length) {
    return `<p class="station-empty">目前沒有拒單紀錄。</p>`;
  }

  return `
    <div class="reject-summary-list">
      ${audits
        .slice(0, 8)
        .map(
          (item) => `
            <article class="reject-summary-card">
              <b>${escapeHtml(item.symbol || station)}</b>
              <p>${escapeHtml(buildRejectNarration(item.reject_layer, item.reject_reason))}</p>
            </article>
          `,
        )
        .join("")}
    </div>
  `;
}

export function renderRoleInspector(state, station, activeRoleIndex = 0) {
  const roles = buildRoleWindows(state, station);
  if (!roles.length) {
    return `<p class="station-empty">目前沒有角色資訊。</p>`;
  }

  const safeIndex = Math.max(0, Math.min(activeRoleIndex, roles.length - 1));
  const activeRole = roles[safeIndex];

  return `
    <div class="role-inspector">
      <nav class="role-list" data-scroll-key="role-list-${station}">
        ${roles
          .map(
            (role, index) => `
              <button type="button" class="role-list-item ${index === safeIndex ? "active" : ""}" data-role-index="${index}">
                <b>${escapeHtml(role.role)}</b>
                <span>${escapeHtml(role.currentTask)}</span>
              </button>
            `,
          )
          .join("")}
      </nav>
      <article class="role-window-card role-window-card--active">
        <header>
          <h4>${escapeHtml(activeRole.role)}</h4>
        </header>
        <div class="role-window-section">
          <span>目前任務</span>
          <p>${escapeHtml(normalizeText(activeRole.currentTask, "目前沒有新的任務。"))}</p>
        </div>
        <div class="role-window-section">
          <span>最新回報</span>
          <p>${escapeHtml(normalizeText(activeRole.latestSpeech, "目前沒有新的回報。"))}</p>
        </div>
        <div class="role-window-section">
          <span>討論重點</span>
          <ul class="station-list compact">
            ${activeRole.discussion.map((item) => `<li>${escapeHtml(normalizeText(item, "目前沒有新的討論重點。"))}</li>`).join("")}
          </ul>
        </div>
      </article>
    </div>
  `;
}

export function renderMeetingReports(state, station) {
  const latestMeeting = getLatestMeeting(state);
  const unitReports = latestMeeting?.unit_reports?.[station] || [];
  if (!unitReports.length) {
    return `<p class="station-empty">目前沒有新的會議報告。</p>`;
  }

  return `
    <div class="unit-report-list">
      ${unitReports
        .map(
          (item) => `
            <article class="unit-report-card">
              <b>${escapeHtml(item.speaker || translateStation(station))}</b>
              <p>${escapeHtml(normalizeText(item.message, "目前沒有新的會議報告。"))}</p>
            </article>
          `,
        )
        .join("")}
    </div>
  `;
}

export function renderStationContextPanels(state, station, options = {}) {
  const title = options.title || `${translateStation(station)} 站內總覽`;
  return `
    <section class="station-briefing-layout">
      ${renderStationOverview(state, station, title)}
      <article class="station-context-card station-context-wide">
        <h3>站內通訊</h3>
        ${renderStationChats(state, station)}
      </article>
      <article class="station-context-card station-context-wide">
        <h3>會議報告</h3>
        ${renderMeetingReports(state, station)}
      </article>
      <article class="station-context-card station-context-wide">
        <h3>拒單摘要</h3>
        ${renderRejectSummary(state, station)}
      </article>
      <article class="station-context-card station-context-wide">
        <h3>AI 角色視窗</h3>
        ${renderRoleInspector(state, station, 0)}
      </article>
    </section>
  `;
}
