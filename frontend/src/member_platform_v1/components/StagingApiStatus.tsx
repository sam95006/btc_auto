import { useEffect, useState } from "react";
import { getStagingApiStatus, type StagingApiStatus } from "../services/stagingApi";

/**
 * Honest, compact binding indicator. It does not reinterpret fixture market
 * data as live data and makes the missing runtime explicit.
 */
export function StagingApiStatus() {
  const [status, setStatus] = useState<StagingApiStatus | null>(null);

  useEffect(() => {
    let active = true;
    void getStagingApiStatus()
      .then((next) => active && setStatus(next))
      .catch(() => active && setStatus(null));
    return () => {
      active = false;
    };
  }, []);

  if (!status) {
    return (
      <p className="mpv1-muted" role="status">
        Staging API unavailable · Runtime not bound
      </p>
    );
  }

  return (
    <p className="mpv1-muted" role="status">
      Staging API {status.health === "OK" && status.readiness ? "ready" : "unavailable"} ·{" "}
      Auth foundation {status.authFoundation} · Runtime not bound
    </p>
  );
}
