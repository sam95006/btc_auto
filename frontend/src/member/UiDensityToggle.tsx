import { useEffect, useState } from "react";
import { loadUiDensity, saveUiDensity, type UiDensity } from "./uiDensityPrefs";
import { useT } from "../i18n";

type Props = {
  density?: UiDensity;
  onDensityChange?: (d: UiDensity) => void;
};

export function UiDensityToggle({ density: controlled, onDensityChange }: Props) {
  const t = useT();
  const [internal, setInternal] = useState<UiDensity>(() => loadUiDensity());
  const density = controlled ?? internal;

  useEffect(() => {
    if (controlled == null) {
      saveUiDensity(internal);
    }
  }, [controlled, internal]);

  const setDensity = (d: UiDensity) => {
    if (onDensityChange) onDensityChange(d);
    else setInternal(d);
    saveUiDensity(d);
    window.dispatchEvent(new CustomEvent("nexus-ui-density", { detail: d }));
  };

  return (
    <div className="nx-ui-density-toggle" role="group" aria-label={t("ui.density.label")}>
      <button
        type="button"
        className={density === "SIMPLE" ? "active" : undefined}
        aria-pressed={density === "SIMPLE"}
        onClick={() => setDensity("SIMPLE")}
      >
        {t("ui.density.simple")}
      </button>
      <button
        type="button"
        className={density === "EXPERT" ? "active" : undefined}
        aria-pressed={density === "EXPERT"}
        onClick={() => setDensity("EXPERT")}
      >
        {t("ui.density.expert")}
      </button>
    </div>
  );
}
