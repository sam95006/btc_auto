import { Link } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import type { ScannerEvent } from "../market/scannerApi";
import {
  clearReadEvents,
  eventTypeLabelZh,
  isHighPriorityEvent,
  loadEventPrefs,
  loadReadEventIds,
  markEventsRead,
  saveEventPrefs,
  type EventPrefs,
} from "../market/eventPrefs";

type Props = {
  open: boolean;
  onClose: () => void;
  events: ScannerEvent[];
  onPrefsChange?: (p: EventPrefs) => void;
};

export function EventCenterDrawer({ open, onClose, events, onPrefsChange }: Props) {
  const [prefs, setPrefs] = useState<EventPrefs>(() => loadEventPrefs());
  const [readIds, setReadIds] = useState(() => loadReadEventIds());

  useEffect(() => {
    if (!open) return;
    const ids = events.map((e) => e.id);
    markEventsRead(ids);
    setReadIds(loadReadEventIds());
  }, [open, events]);

  const unread = useMemo(
    () => events.filter((e) => !readIds.has(e.id)).length,
    [events, readIds],
  );

  if (!open) return null;

  const patch = (partial: Partial<EventPrefs>) => {
    const next = { ...prefs, ...partial, version: 1 as const };
    setPrefs(next);
    saveEventPrefs(next);
    onPrefsChange?.(next);
  };

  return (
    <div className="nx-drawer-root" role="dialog" aria-modal="true" aria-label="事件中心">
      <button type="button" className="nx-drawer-backdrop" aria-label="關閉" onClick={onClose} />
      <aside className="nx-drawer-panel nx-motion-ok">
        <header className="nx-drawer-head">
          <h2>
            事件中心 {unread > 0 ? <span className="nx-unread-pill">{unread}</span> : null}
          </h2>
          <button type="button" className="nx-text-btn" onClick={onClose}>
            關閉
          </button>
        </header>
        <div className="nx-drawer-body">
          <div className="nx-notify-opts">
            <label>
              <input
                type="checkbox"
                checked={prefs.toast}
                onChange={(e) => patch({ toast: e.target.checked })}
              />
              Toast
            </label>
            <label>
              <input
                type="checkbox"
                checked={prefs.sound}
                onChange={(e) => patch({ sound: e.target.checked })}
              />
              聲音
            </label>
            <label>
              <input
                type="checkbox"
                checked={prefs.browserNotify}
                onChange={async (e) => {
                  const on = e.target.checked;
                  if (on && "Notification" in window && Notification.permission !== "granted") {
                    await Notification.requestPermission();
                  }
                  patch({ browserNotify: on });
                }}
              />
              瀏覽器通知
            </label>
            <button
              type="button"
              className="nx-text-btn"
              onClick={() => {
                clearReadEvents();
                setReadIds(new Set());
              }}
            >
              清除已讀
            </button>
          </div>
          <p className="muted sm">聲音與瀏覽器通知預設關閉；高優先僅用於新進榜／確認／過熱。</p>
          <ul className="nx-event-list">
            {events.length === 0 ? (
              <li className="muted">尚無事件</li>
            ) : (
              events.map((ev) => (
                <li key={ev.id} className={isHighPriorityEvent(ev) ? "nx-ev-high" : undefined}>
                  <Link to={`/market/${ev.symbol}`} onClick={onClose}>
                    <span className="mono">{ev.symbol.replace("USDT", "")}</span>
                    <span>
                      <strong>{eventTypeLabelZh(ev.type)}</strong> · {ev.explanation}
                    </span>
                    <time className="muted">{new Date(ev.timestamp).toLocaleTimeString()}</time>
                  </Link>
                </li>
              ))
            )}
          </ul>
        </div>
      </aside>
    </div>
  );
}

export function EventBellButton({
  unread,
  onClick,
}: {
  unread: number;
  onClick: () => void;
}) {
  return (
    <button type="button" className="mtt-icon nx-bell" onClick={onClick} aria-label="事件中心" title="事件中心">
      🔔
      {unread > 0 ? <span className="nx-bell-count">{unread > 9 ? "9+" : unread}</span> : null}
    </button>
  );
}
