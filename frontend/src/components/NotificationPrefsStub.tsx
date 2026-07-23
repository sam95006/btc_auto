import { useState } from "react";
import {
  loadNotificationPrefs,
  saveNotificationPrefs,
  type NotificationPrefs,
} from "../market/notificationPrefs";

/**
 * Notification preference UI stub — local only, anti-spam defaults.
 * Does not send push or sound unless user explicitly opts in.
 */
export function NotificationPrefsStub() {
  const [prefs, setPrefs] = useState<NotificationPrefs>(() => loadNotificationPrefs());
  const [saved, setSaved] = useState(false);

  const patch = (partial: Partial<NotificationPrefs>) => {
    const next = { ...prefs, ...partial };
    setPrefs(next);
    saveNotificationPrefs(next);
    setSaved(true);
    window.setTimeout(() => setSaved(false), 1500);
  };

  return (
    <section className="nx-p7-block nx-notif-prefs" aria-label="Notification preferences">
      <h2 className="nx-sec-title">通知偏好（本地）</h2>
      <p className="muted sm">
        僅偏好設定 stub · 預設 digest-only · 不會主動推播或播音（防 spam）。
      </p>
      <div className="nx-notif-grid">
        <label>
          <input
            type="checkbox"
            checked={prefs.muted}
            onChange={(e) => patch({ muted: e.target.checked })}
          />{" "}
          全部靜音
        </label>
        <label>
          <input
            type="checkbox"
            checked={prefs.digestOnly}
            onChange={(e) => patch({ digestOnly: e.target.checked })}
          />{" "}
          僅摘要（預設開）
        </label>
        <label>
          <input
            type="checkbox"
            checked={prefs.toast}
            disabled={prefs.muted}
            onChange={(e) => patch({ toast: e.target.checked })}
          />{" "}
          Toast（事件中心）
        </label>
        <label>
          <input
            type="checkbox"
            checked={prefs.sound}
            disabled={prefs.muted || prefs.digestOnly}
            onChange={(e) => patch({ sound: e.target.checked })}
          />{" "}
          聲音（預設關）
        </label>
        <label>
          <input
            type="checkbox"
            checked={prefs.browserNotify}
            disabled={prefs.muted || prefs.digestOnly}
            onChange={(e) => patch({ browserNotify: e.target.checked })}
          />{" "}
          瀏覽器通知（預設關）
        </label>
      </div>
      {saved ? <p className="muted sm">已儲存至 localStorage</p> : null}
    </section>
  );
}
