import { useEffect, useState } from "react";
import { NEXUS_UI_BUILD_INFO } from "../demo/buildInfo";

type Props = {
  open: boolean;
  onClose: () => void;
};

/**
 * System / research safety drawer — HOLD & Stage 4.19 live here, not in primary top bar.
 */
export function SystemStatusDrawer({ open, onClose }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  const b = NEXUS_UI_BUILD_INFO;

  return (
    <div className="nx-drawer-root" role="dialog" aria-modal="true" aria-label="系統狀態">
      <button type="button" className="nx-drawer-backdrop" aria-label="關閉" onClick={onClose} />
      <aside className="nx-drawer-panel nx-motion-ok">
        <header className="nx-drawer-head">
          <h2>系統狀態</h2>
          <button type="button" className="nx-text-btn" onClick={onClose}>
            關閉
          </button>
        </header>
        <div className="nx-drawer-body">
          <p className="nx-status-line">即時市場資料 · 研究模式 · 不執行交易</p>
          <dl className="nx-kv">
            <div>
              <dt>Backend</dt>
              <dd>HOLD</dd>
            </div>
            <div>
              <dt>Stage 4.19</dt>
              <dd>BLOCKED</dd>
            </div>
            <div>
              <dt>Radar Auto Trade</dt>
              <dd>OFF</dd>
            </div>
            <div>
              <dt>Defensive Mode</dt>
              <dd>ON</dd>
            </div>
            <div>
              <dt>Private API</dt>
              <dd>false</dd>
            </div>
            <div>
              <dt>UI Build</dt>
              <dd className="mono">{b.displayLabel}</dd>
            </div>
            <div>
              <dt>Build marker</dt>
              <dd className="mono muted">{b.buildMarker}</dd>
            </div>
          </dl>
          <p className="muted sm">
            以上為研究／安全狀態，不是交易指令。市場候選不等於既有 Recommendation，也不觸發下單。
          </p>
        </div>
      </aside>
    </div>
  );
}

export function useSystemStatusOpen() {
  const [open, setOpen] = useState(false);
  return { open, setOpen, openStatus: () => setOpen(true), closeStatus: () => setOpen(false) };
}
