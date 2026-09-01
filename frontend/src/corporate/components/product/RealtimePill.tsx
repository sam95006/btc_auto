/** Connection-state pill for the realtime market link (live / polling / reconnecting). */
import { useLocale } from "../../i18n";
import type { RealtimeStatus } from "../../context/MarketContext";

export function RealtimePill({ rt }: { rt: RealtimeStatus }) {
  const { t } = useLocale();
  const label = rt === "live" ? t("rt_live") : rt === "polling" ? t("rt_polling") : t("rt_reconnect");
  return (
    <span className="corp-rt" data-rt={rt} data-testid="realtime-pill" role="status" aria-live="polite">
      {label} · {t("rt_source")} binance_usdm_public
    </span>
  );
}
