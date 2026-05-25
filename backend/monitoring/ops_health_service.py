from __future__ import annotations

import json
import os
import time
import urllib.request


class OpsHealthService:
    """SLO-style health + optional webhook alerts (no mainnet switch)."""

    def __init__(self):
        self._last_webhook_at = 0.0
        self._webhook_cooldown_sec = max(60, int(os.getenv("NEXUS_OPS_WEBHOOK_COOLDOWN_SEC", "900") or 900))

    def build_report(self, snapshot, embedded_worker_started=False, embedded_worker_error=None):
        snapshot = dict(snapshot or {})
        system = dict(snapshot.get("system") or {})
        live_sync = dict(snapshot.get("live_sync") or {})
        decision = dict(snapshot.get("decision_summary") or {})
        maturity = dict(snapshot.get("maturity_radar") or {})

        sync_fresh = self._sync_fresh(live_sync)
        checks = {
            "worker_online": bool(embedded_worker_started) and not embedded_worker_error,
            "not_trading_paused": not bool(system.get("trading_paused")),
            "exchange_sync_fresh": sync_fresh,
            "futures_configured": bool(decision.get("futures_enabled")),
            "maturity_target_met": bool(maturity.get("target_80_all_dimensions")),
        }
        passed = sum(1 for item in checks.values() if item)
        total = len(checks)
        score = round(passed / max(total, 1) * 100, 1)
        status = "healthy" if score >= 85 else "degraded" if score >= 65 else "critical"

        return {
            "status": status,
            "slo_score": score,
            "checks": checks,
            "passed": passed,
            "total": total,
            "embedded_worker_error": embedded_worker_error,
            "data_dir": os.getenv("NEXUS_DATA_DIR", ""),
            "webhook_configured": bool(os.getenv("NEXUS_OPS_WEBHOOK_URL", "").strip()),
            "note": "營運成熟度以告警與 SLO 為主；主網切換需人工核准。",
        }

    def maybe_alert(self, report, previous_status=None):
        url = str(os.getenv("NEXUS_OPS_WEBHOOK_URL", "") or "").strip()
        if not url:
            return False
        status = str(report.get("status") or "")
        if status == "healthy":
            return False
        if previous_status == status:
            return False
        now = time.time()
        if now - self._last_webhook_at < self._webhook_cooldown_sec:
            return False
        payload = {
            "text": f"[NEXUS] ops {status} · SLO {report.get('slo_score')}% · checks {report.get('passed')}/{report.get('total')}",
            "status": status,
            "slo_score": report.get("slo_score"),
            "checks": report.get("checks"),
        }
        try:
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=8)
            self._last_webhook_at = now
            return True
        except Exception:
            return False

    def _sync_fresh(self, live_sync):
        updated_ms = int(live_sync.get("updated_at_ms") or 0)
        if not updated_ms:
            return False
        return (time.time() * 1000 - updated_ms) < 120_000
