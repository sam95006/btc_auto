import { useEffect, useState } from "react";
import { loadUiDensity, saveUiDensity, type UiDensity } from "./uiDensityPrefs";
import { useT } from "../i18n";

type Props = {
  density?: UiDensity;
  onDensityChange?: (d: UiDensity) => void;
  className?: string;
};

/**
 * Polished 簡潔 / 專業 segmented control.
 * Density is independent of membership plan.
 */
export function UiDensityToggle({ density: controlled, onDensityChange, className }: Props) {
  const t = useT();
  const [internal, setInternal] = useState<UiDensity>(() => loadUiDensity());
  const density = controlled ?? internal;

  useEffect(() => {
    if (controlled == null) {
      saveUiDensity(internal);
    }
  }, [controlled, internal]);

  useEffect(() => {
    const onExt = (e: Event) => {
      const d = (e as CustomEvent<UiDensity>).detail;
      if (d === "SIMPLE" || d === "EXPERT") {
        if (controlled == null) setInternal(d);
      }
    };
    window.addEventListener("nexus-ui-density", onExt);
    return () => window.removeEventListener("nexus-ui-density", onExt);
  }, [controlled]);

  const setDensity = (d: UiDensity) => {
    if (onDensityChange) onDensityChange(d);
    else setInternal(d);
    saveUiDensity(d);
    window.dispatchEvent(new CustomEvent("nexus-ui-density", { detail: d }));
  };

  return (
    <div
      className={`nx-ui-density-toggle${className ? ` ${className}` : ""}`}
      role="group"
      aria-label={t("ui.density.label")}
      data-testid="ui-density-toggle"
    >
      <button
        type="button"
        className={density === "SIMPLE" ? "active" : undefined}
        aria-pressed={density === "SIMPLE"}
        data-density="SIMPLE"
        onClick={() => setDensity("SIMPLE")}
      >
        {t("ui.density.simple")}
      </button>
      <button
        type="button"
        className={density === "EXPERT" ? "active" : undefined}
        aria-pressed={density === "EXPERT"}
        data-density="EXPERT"
        onClick={() => setDensity("EXPERT")}
      >
        {t("ui.density.expert")}
      </button>
    </div>
  );
}
