import { sendStationChat } from "../api_client.js?v=20260521a";
import { buildStationConversation, escapeHtml, normalizeText, translateStation } from "../utils/presentation.js?v=20260521a";

const CHANNELS = ["WORLD", "HQ", "BTC", "ETH", "SOL", "PEPE", "RADAR", "NEWS", "RISK"];
const CHANNEL_SHORT = { WORLD: "世界", HQ: "HQ", BTC: "BTC", ETH: "ETH", SOL: "SOL", PEPE: "PEPE", RADAR: "雷達", NEWS: "新聞", RISK: "風控" };

const SPEAKER_CLASS = [
  [/指揮|總部/, "game-chat-speaker--hq"],
  [/BTC/, "game-chat-speaker--btc"],
  [/ETH/, "game-chat-speaker--eth"],
  [/SOL/, "game-chat-speaker--sol"],
  [/PEPE/, "game-chat-speaker--pepe"],
  [/雷達|巨鯨/, "game-chat-speaker--radar"],
  [/新聞/, "game-chat-speaker--news"],
  [/風控/, "game-chat-speaker--risk"],
];

function formatTime(ts) {
  const m = String(ts || "").match(/(\d{2}:\d{2})/);
  return m ? m[1] : "--:--";
}

function speakerClass(name, source) {
  if (String(source || "").includes("玩家")) return "game-chat-speaker--player";
  const hit = SPEAKER_CLASS.find(([re]) => re.test(String(name || "")));
  return hit ? hit[1] : "game-chat-speaker--default";
}

function renderLine(row) {
  const imp = String(row.importance || "info").toLowerCase();
  const isPlayer = String(row.source || "").includes("玩家");
  return `
    <div class="game-chat-line game-chat-line--${imp} ${isPlayer ? "game-chat-line--player" : ""}">
      <span class="game-chat-time">${escapeHtml(formatTime(row.timestamp))}</span>
      <span class="game-chat-speaker ${speakerClass(row.speaker, row.source)}">${escapeHtml(row.speaker || "系統")}</span>
      <span class="game-chat-msg">${escapeHtml(normalizeText(row.message, "…"))}</span>
    </div>
  `;
}

function renderLogHtml(rows) {
  if (!rows.length) {
    return `<p class="game-chat-empty">輸入訊息，站長或 AI 會回覆。</p>`;
  }
  return rows.map(renderLine).join("");
}

function bindChatEvents(root, uiState, updateUiState) {
  root.querySelector("[data-chat-toggle]")?.addEventListener("click", () => {
    updateUiState({ minimized: !uiState.minimized });
  });
  root.querySelectorAll("[data-chat-station]").forEach((btn) => {
    btn.addEventListener("click", () => {
      updateUiState({ activeStation: btn.dataset.chatStation, minimized: false });
    });
  });

  const form = root.querySelector("[data-chat-form]");
  const input = root.querySelector("[data-chat-input]");
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const value = input?.value || "";
    if (!String(value).trim()) return;
    if (input) input.disabled = true;
    try {
      await sendStationChat(uiState.activeStation || "WORLD", value);
      updateUiState({ minimized: false });
    } catch (error) {
      console.error("[chat]", error);
    } finally {
      if (input) {
        input.disabled = false;
        input.value = "";
        input.focus();
      }
    }
  });
}

function mountChatShell(root, state, uiState) {
  const activeStation = uiState.activeStation || "WORLD";
  const minimized = Boolean(uiState.minimized);
  const rows = buildStationConversation(state, activeStation).slice(-28);
  const hint = activeStation === "WORLD" ? "各站長跨站討論" : `${translateStation(activeStation)} 站內討論`;

  root.innerHTML = `
    <div class="chat-dock ${minimized ? "is-minimized" : "is-open"}" data-chat-shell data-station="${activeStation}" data-minimized="${minimized}">
      ${
        minimized
          ? `<button type="button" class="game-chat-fab" data-chat-toggle title="展開聊天室">
               <span class="game-chat-fab-ring"></span><span class="game-chat-fab-core"></span>
               <span class="game-chat-fab-label">${escapeHtml(CHANNEL_SHORT[activeStation] || activeStation)}</span>
             </button>`
          : `<section class="game-chat-panel">
               <header class="game-chat-header">
                 <div class="game-chat-title"><span class="game-chat-title-kicker">COMMS</span><strong>${escapeHtml(translateStation(activeStation))}</strong></div>
                 <div class="game-chat-header-actions">
                   <span class="game-chat-hint">${escapeHtml(hint)}</span>
                   <button type="button" class="game-chat-btn" data-chat-toggle title="收合">—</button>
                 </div>
               </header>
               <nav class="game-chat-channels">
                 ${CHANNELS.map((ch) => `<button type="button" class="game-chat-channel ${ch === activeStation ? "active" : ""}" data-chat-station="${ch}">${escapeHtml(CHANNEL_SHORT[ch] || ch)}</button>`).join("")}
               </nav>
               <div class="game-chat-log" data-chat-log>${renderLogHtml(rows)}</div>
               <form class="game-chat-compose" data-chat-form>
                 <input class="game-chat-input" data-chat-input maxlength="500" placeholder="以指揮官身份發言…" autocomplete="off" />
                 <button type="submit" class="game-chat-send">發送</button>
               </form>
               <footer class="game-chat-footer"><span class="game-chat-footer-tag">[${escapeHtml(translateStation(activeStation))}]</span><span>Enter 發送</span></footer>
             </section>`
      }
    </div>
  `;
  bindChatEvents(root, uiState, updateUiState);
}

export function renderChatDock(root, state, uiState, updateUiState) {
  if (!root) return;

  const activeStation = uiState.activeStation || "WORLD";
  const minimized = Boolean(uiState.minimized);
  const rows = buildStationConversation(state, activeStation).slice(-28);

  const shell = root.querySelector("[data-chat-shell]");
  const sameLayout =
    shell &&
    shell.dataset.station === activeStation &&
    shell.dataset.minimized === String(minimized);

  if (!sameLayout) {
    const input = root.querySelector("[data-chat-input]");
    const saved = input?.value || "";
    const focused = document.activeElement === input;
    mountChatShell(root, state, uiState);
    const nextInput = root.querySelector("[data-chat-input]");
    if (nextInput && saved) {
      nextInput.value = saved;
      if (focused) nextInput.focus();
    }
    const log = root.querySelector("[data-chat-log]");
    if (log) log.scrollTop = log.scrollHeight;
    return;
  }

  const log = root.querySelector("[data-chat-log]");
  if (log) {
    log.innerHTML = renderLogHtml(rows);
    log.scrollTop = log.scrollHeight;
  }
}
