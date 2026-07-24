import { useState } from "react";
import {
  loadNotificationPrefs,
  saveNotificationPrefs,
  isBrowserPushGranted,
  notificationPrefsDisclosure,
  type NotificationPrefs,
} from "../market/notificationPrefs";

/**
 * Notification preference UI (Product 7.2) — local only, anti-spam defaults.
 * - Shows actual browser Notification.permission (never claims granted without it).
 * - Never enables browser push without real OS/browser permission.
 * - Clearly labeled LOCAL_ONLY — no cross-device sync.
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

  const pushGranted = isBrowserPushGranted();
  const permLabel =
    prefs.browserPushPermission === "granted"
      ? "已授權 ✓"
      : prefs.browserPushPermission === "denied"
        ? "已拒絕（需在瀏覽器手動解除）"
        : prefs.browserPushPermission === "unsupported"
          ? "瀏覽器不支援"
          : "尚未詢問";

  return (
    <section className="nx-p7-block nx-notif-prefs" aria-label="Notification preferences">
      <h2 className="nx-sec-title">通知偏好</h2>
      <p className="muted sm">
        LOCAL_ONLY · 僅存於本瀏覽器 · 預設 digest-only（防 spam） · 不跨裝置
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
            disabled={prefs.muted || prefs.digestOnly || !pushGranted}
            onChange={(e) => patch({ browserNotify: e.target.checked })}
          />{" "}
          瀏覽器通知（預設關）
          {!pushGranted ? (
            <span className="muted sm"> — 需先授權推播</span>
          ) : null}
        </label>
      </div>
      {/* Always show actual permission status — never claim enabled without grant */}
      <p className="muted sm">
        瀏覽器推播許可：<strong>{permLabel}</strong>
        {prefs.browserPushPermission === "default" ? (
          <> · 勾選後需允許瀏覽器推播彈窗才能啟用</>
        ) : null}
      </p>
      <p className="muted sm">{notificationPrefsDisclosure()}</p>
      {saved ? <p className="muted sm">✓ 已儲存至 localStorage</p> : null}
    </section>
  );
}
