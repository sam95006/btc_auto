export function renderAlertPanel(root, state) {
  const system = state.system || {};
  const paused = Boolean(system.trading_paused);
  const title = "系統狀態";
  const detail = paused ? "暫停中" : "運行中";
  const tone = paused ? "warn active" : "healthy";

  root.className = `alert-panel ${tone}`;
  root.dataset.scrollKey = "main-alert-panel";
  root.innerHTML = `
    <div class="alert-orb"></div>
    <div>
      <span>${title}</span>
      <strong>${detail}</strong>
    </div>
  `;
}
