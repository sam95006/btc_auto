"""Read-only autonomous Demo operations status contract (no secrets)."""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class OpsState(str, Enum):
    SCANNING = "SCANNING"
    NO_QUALIFIED_CANDIDATE = "NO_QUALIFIED_CANDIDATE"
    CANDIDATE_SELECTED = "CANDIDATE_SELECTED"
    ORDER_PENDING = "ORDER_PENDING"
    POSITION_OPEN = "POSITION_OPEN"
    PROTECTED = "PROTECTED"
    EXIT_PENDING = "EXIT_PENDING"
    CLOSED = "CLOSED"
    PAUSED_RISK_GATE = "PAUSED_RISK_GATE"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    EMERGENCY_STOPPED = "EMERGENCY_STOPPED"


OPS_STATE_ZH: dict[str, str] = {
    OpsState.SCANNING.value: "正在掃描市場",
    OpsState.NO_QUALIFIED_CANDIDATE.value: "尚無合格交易機會",
    OpsState.CANDIDATE_SELECTED.value: "已選定交易候選",
    OpsState.ORDER_PENDING.value: "訂單送出中",
    OpsState.POSITION_OPEN.value: "持倉中",
    OpsState.PROTECTED.value: "持倉中，SL／TP 已保護",
    OpsState.EXIT_PENDING.value: "平倉處理中",
    OpsState.CLOSED.value: "最近交易已完成",
    OpsState.PAUSED_RISK_GATE.value: "風控暫停",
    OpsState.RECOVERY_REQUIRED.value: "需要對帳恢復",
    OpsState.SESSION_EXPIRED.value: "Demo 授權已到期",
    OpsState.EMERGENCY_STOPPED.value: "緊急停止",
}

LIFECYCLE_STEPS = (
    "SCANNED",
    "CANDIDATE",
    "SELECTED",
    "ORDER_SENT",
    "ACKNOWLEDGED",
    "FILLED",
    "PROTECTED",
    "EXITED",
    "RECONCILED",
    "REFLECTION_CREATED",
)


def resolve_deployment_commit() -> str:
    for key in (
        "ZEABUR_GIT_COMMIT",
        "ZEABUR_COMMIT_SHA",
        "GIT_COMMIT",
        "DEPLOYMENT_COMMIT",
        "COMMIT_SHA",
        "SOURCE_VERSION",
        "RAILWAY_GIT_COMMIT_SHA",
    ):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            return raw[:64]
    return ""


def resolve_deployment_id_present() -> bool:
    return bool(
        (os.environ.get("ZEABUR_DEPLOYMENT_ID") or os.environ.get("ZEABUR_SERVICE_ID") or "").strip()
    )


def _ops_path() -> Path | None:
    try:
        from backend.nexus_research.boot_identity import research_data_dir

        root = research_data_dir()
        if root is None:
            return None
        return root / "autonomous_ops_state.json"
    except Exception:
        return None


@dataclass
class AutonomousOpsStore:
    """Persisted scan / trade ops snapshot for UI continuity across restarts."""

    last_scan_at_ms: int | None = None
    last_candidate_at_ms: int | None = None
    last_order_at_ms: int | None = None
    last_reflection_at_ms: int | None = None
    last_closed_at_ms: int | None = None
    symbols_scanned: int = 0
    tradable_symbols: int = 0
    eligible_candidates: int = 0
    top_candidate: dict[str, Any] | None = None
    last_block_reasons: list[str] = field(default_factory=list)
    last_trade: dict[str, Any] | None = None
    last_reflection: dict[str, Any] | None = None
    lifecycle_completed: list[str] = field(default_factory=list)
    scan_history_ms: list[int] = field(default_factory=list)
    daily_pnl: float | None = None
    weekly_pnl: float | None = None
    drawdown: float | None = None
    consecutive_losses: int | None = None
    capital_tier: str = "VALIDATION"
    risk_tier: str = "0.5pct"
    updated_at_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "lastScanAtMs": self.last_scan_at_ms,
            "lastCandidateAtMs": self.last_candidate_at_ms,
            "lastOrderAtMs": self.last_order_at_ms,
            "lastReflectionAtMs": self.last_reflection_at_ms,
            "lastClosedAtMs": self.last_closed_at_ms,
            "symbolsScanned": self.symbols_scanned,
            "tradableSymbols": self.tradable_symbols,
            "eligibleCandidates": self.eligible_candidates,
            "topCandidate": self.top_candidate,
            "lastBlockReasons": list(self.last_block_reasons),
            "lastTrade": self.last_trade,
            "lastReflection": self.last_reflection,
            "lifecycleCompleted": list(self.lifecycle_completed),
            "scanHistoryMs": list(self.scan_history_ms[-12:]),
            "dailyPnl": self.daily_pnl,
            "weeklyPnl": self.weekly_pnl,
            "drawdown": self.drawdown,
            "consecutiveLosses": self.consecutive_losses,
            "capitalTier": self.capital_tier,
            "riskTier": self.risk_tier,
            "updatedAtMs": self.updated_at_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AutonomousOpsStore":
        data = data or {}
        return cls(
            last_scan_at_ms=data.get("lastScanAtMs"),
            last_candidate_at_ms=data.get("lastCandidateAtMs"),
            last_order_at_ms=data.get("lastOrderAtMs"),
            last_reflection_at_ms=data.get("lastReflectionAtMs"),
            last_closed_at_ms=data.get("lastClosedAtMs"),
            symbols_scanned=int(data.get("symbolsScanned") or 0),
            tradable_symbols=int(data.get("tradableSymbols") or 0),
            eligible_candidates=int(data.get("eligibleCandidates") or 0),
            top_candidate=data.get("topCandidate"),
            last_block_reasons=list(data.get("lastBlockReasons") or []),
            last_trade=data.get("lastTrade"),
            last_reflection=data.get("lastReflection"),
            lifecycle_completed=list(data.get("lifecycleCompleted") or []),
            scan_history_ms=[int(x) for x in (data.get("scanHistoryMs") or [])][-12:],
            daily_pnl=data.get("dailyPnl"),
            weekly_pnl=data.get("weeklyPnl"),
            drawdown=data.get("drawdown"),
            consecutive_losses=data.get("consecutiveLosses"),
            capital_tier=str(data.get("capitalTier") or "VALIDATION"),
            risk_tier=str(data.get("riskTier") or "0.5pct"),
            updated_at_ms=int(data.get("updatedAtMs") or 0),
        )


_STORE: AutonomousOpsStore | None = None
_STORE_LOCK = threading.Lock()


def get_ops_store() -> AutonomousOpsStore:
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = _load_store()
        return _STORE


def _load_store() -> AutonomousOpsStore:
    path = _ops_path()
    if path is None or not path.is_file():
        return AutonomousOpsStore()
    try:
        return AutonomousOpsStore.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return AutonomousOpsStore()


def save_ops_store(store: AutonomousOpsStore | None = None) -> None:
    store = store or get_ops_store()
    store.updated_at_ms = int(time.time() * 1000)
    path = _ops_path()
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(store.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def record_scan_result(result: dict[str, Any]) -> AutonomousOpsStore:
    store = get_ops_store()
    now = int(time.time() * 1000)
    store.last_scan_at_ms = now
    store.scan_history_ms = (store.scan_history_ms + [now])[-12:]
    universe = result.get("universe") or {}
    store.symbols_scanned = int(universe.get("totalContracts") or universe.get("total") or 0)
    store.tradable_symbols = int(
        universe.get("tradableContracts")
        or universe.get("tradable")
        or 0
    )
    candidates = result.get("candidates") or []
    store.eligible_candidates = len(candidates) if isinstance(candidates, list) else int(
        result.get("eligibleCandidates") or 0
    )
    top = result.get("top")
    store.top_candidate = top if isinstance(top, dict) else None
    if store.top_candidate:
        store.last_candidate_at_ms = now
        if "SCANNED" not in store.lifecycle_completed:
            store.lifecycle_completed.append("SCANNED")
        if "CANDIDATE" not in store.lifecycle_completed:
            store.lifecycle_completed.append("CANDIDATE")
        if "SELECTED" not in store.lifecycle_completed:
            store.lifecycle_completed.append("SELECTED")
    elif "SCANNED" not in store.lifecycle_completed:
        store.lifecycle_completed.append("SCANNED")
    blocker = result.get("blocker")
    # Persist raw historical reason list; current read-model may clear stale exposure blockers.
    store.last_block_reasons = [str(blocker)] if blocker else []
    if result.get("orderSent"):
        store.last_order_at_ms = now
        for step in ("ORDER_SENT", "ACKNOWLEDGED", "FILLED"):
            if step not in store.lifecycle_completed:
                store.lifecycle_completed.append(step)
    save_ops_store(store)
    return store


def record_reflection(reflection: dict[str, Any], trade: dict[str, Any] | None = None) -> None:
    store = get_ops_store()
    now = int(time.time() * 1000)
    store.last_reflection = reflection
    store.last_reflection_at_ms = now
    store.last_closed_at_ms = now
    if trade:
        store.last_trade = trade
    for step in ("EXITED", "RECONCILED", "REFLECTION_CREATED"):
        if step not in store.lifecycle_completed:
            store.lifecycle_completed.append(step)
    save_ops_store(store)


def derive_ops_state(
    *,
    session: dict[str, Any] | None,
    controller: dict[str, Any] | None,
    position_count: int,
    open_order_count: int,
    protection_active: bool,
    exit_pending: bool,
    eligible_candidates: int,
    top_candidate: dict[str, Any] | None,
    recovery_required: bool,
    risk_paused: bool,
    last_closed_recent: bool,
) -> OpsState:
    if session and session.get("emergencyStopped"):
        return OpsState.EMERGENCY_STOPPED
    if recovery_required:
        return OpsState.RECOVERY_REQUIRED
    if session is None:
        # Scan-only allowed without session; still surface SESSION_EXPIRED if we had one.
        pass
    elif session.get("expired") or not session.get("active"):
        if position_count <= 0:
            return OpsState.SESSION_EXPIRED
    if risk_paused:
        return OpsState.PAUSED_RISK_GATE
    if exit_pending:
        return OpsState.EXIT_PENDING
    if position_count > 0:
        return OpsState.PROTECTED if protection_active else OpsState.POSITION_OPEN
    if open_order_count > 0:
        return OpsState.ORDER_PENDING
    if top_candidate and eligible_candidates > 0:
        allow = True
        if isinstance(top_candidate.get("allowTrade"), bool):
            allow = bool(top_candidate.get("allowTrade"))
        if allow:
            return OpsState.CANDIDATE_SELECTED
        return OpsState.NO_QUALIFIED_CANDIDATE
    if last_closed_recent and not (controller or {}).get("running"):
        return OpsState.CLOSED
    if (controller or {}).get("running"):
        # Flat + running: homepage should read as actively working.
        if eligible_candidates == 0 and top_candidate is None:
            return OpsState.SCANNING
        return OpsState.SCANNING
    if last_closed_recent:
        return OpsState.CLOSED
    if eligible_candidates == 0:
        return OpsState.NO_QUALIFIED_CANDIDATE
    return OpsState.SCANNING


def _paper_status_safe() -> dict[str, Any]:
    out: dict[str, Any] = {
        "paperStatus": None,
        "ledgerValid": None,
        "v2Preserved": True,
    }
    try:
        from backend.nexus_research.paper_activation import get_active_paper_session

        sess = get_active_paper_session() or {}
        out["paperStatus"] = sess.get("state")
    except Exception:
        pass
    try:
        from backend.nexus_research.durable_ledger import (
            ACCOUNT_PAPER_MAIN_V1,
            SOURCE_PAPER,
            get_durable_ledger,
        )

        acct = get_durable_ledger(ACCOUNT_PAPER_MAIN_V1, source=SOURCE_PAPER)
        chain = acct.chain_report()
        out["ledgerValid"] = bool(chain.get("chainValid"))
    except Exception:
        pass
    return out


def _protection_from_orders(open_orders: list[dict[str, Any]], positions: list[dict[str, Any]]) -> bool:
    if not positions:
        return False
    # Conditional / Stop orders typically indicate exchange-side SL/TP.
    for o in open_orders or []:
        typ = str(o.get("orderType") or o.get("stopOrderType") or "").lower()
        reduce = o.get("reduceOnly")
        if "stop" in typ or "tp" in typ or "sl" in typ or reduce is True:
            return True
        if str(o.get("orderStatus") or "").lower() == "untriggered":
            return True
    return False


def build_operations_status(*, include_snapshot: bool = True) -> dict[str, Any]:
    """Full read-only ops contract for UI + Live SoT."""
    from backend.nexus_research.demo_autonomous.controller import get_autonomous_controller
    from backend.nexus_research.demo_autonomous.session_authorization import (
        autonomous_enabled_from_env,
        get_authorization_validator,
    )

    now = int(time.time() * 1000)
    auth = get_authorization_validator()
    sess = auth.session
    session_pub = sess.to_public_dict() if sess else None
    controller = get_autonomous_controller().to_dict()
    store = get_ops_store()

    snap: dict[str, Any] = {}
    position_count = 0
    open_order_count = 0
    positions: list[dict[str, Any]] = []
    open_orders: list[dict[str, Any]] = []
    demo_equity = None
    available_balance = None
    fingerprint = ""
    recovery_required = False
    if include_snapshot:
        try:
            from backend.nexus_research.demo_exchange.account_snapshot import capture_account_snapshot

            captured = capture_account_snapshot()
            snap = captured.to_dict()
            positions = list(snap.get("positions") or [])
            open_orders = list(snap.get("open_orders") or [])
            position_count = len([p for p in positions if float(p.get("size") or 0) > 0])
            open_order_count = len(open_orders)
            demo_equity = snap.get("total_equity")
            available_balance = snap.get("available_balance")
            fingerprint = str(snap.get("fingerprint") or "")
            if "EXISTING_ACCOUNT_STATE_REQUIRES_REVIEW" in (snap.get("review_flags") or []):
                recovery_required = True
            if snap.get("status") == "EXISTING_ACCOUNT_STATE_REQUIRES_REVIEW":
                recovery_required = position_count > 1 or open_order_count > 5
        except Exception as exc:
            snap = {"status": "SNAPSHOT_UNAVAILABLE", "error": type(exc).__name__, "secret_safe": True}

    protection_active = _protection_from_orders(open_orders, positions)
    health = (controller.get("health") or {})
    risk_paused = bool(health.get("dailyLossPaused") or health.get("weeklyDdPaused"))
    exit_pending = bool(store.last_block_reasons and "exit" in str(store.last_block_reasons).lower())
    last_closed_recent = bool(
        store.last_closed_at_ms and (now - int(store.last_closed_at_ms)) < 15 * 60 * 1000
    )

    ops_state = derive_ops_state(
        session=session_pub,
        controller=controller,
        position_count=position_count,
        open_order_count=open_order_count,
        protection_active=protection_active,
        exit_pending=exit_pending,
        eligible_candidates=store.eligible_candidates,
        top_candidate=store.top_candidate,
        recovery_required=recovery_required,
        risk_paused=risk_paused,
        last_closed_recent=last_closed_recent,
    )

    scan_hist = store.scan_history_ms
    # Wall-clock freshness — do not treat frozen history as "progressing".
    scan_age_ms = (
        max(0, now - int(store.last_scan_at_ms)) if store.last_scan_at_ms else None
    )
    scan_progressing = bool(
        scan_age_ms is not None and scan_age_ms < 120_000 and len(scan_hist) >= 1
    )

    boot: dict[str, Any] = {}
    try:
        from backend.nexus_research.boot_identity import get_boot_identity

        boot = get_boot_identity()
    except Exception:
        boot = {}

    paper = _paper_status_safe()
    deploy_commit = resolve_deployment_commit()

    # Effective auto-send is env-gated only (fail-closed when missing/false).
    auto_send = False
    try:
        if os.environ.get("NEXUS_AUTONOMOUS_DEMO_AUTO_SEND", "").strip().lower() in (
            "1",
            "true",
            "yes",
        ):
            auto_send = True
    except Exception:
        auto_send = False

    # Operator-facing headline (never "正在交易中" when flat).
    if session_pub is None or session_pub.get("expired") or not session_pub.get("active"):
        if ops_state == OpsState.EMERGENCY_STOPPED:
            headline_zh = "緊急停止"
        else:
            headline_zh = "自動Demo交易：待啟用"
        order_status_zh = "等待 Demo Session"
    elif auto_send and position_count == 0 and ops_state == OpsState.CANDIDATE_SELECTED:
        headline_zh = "自動Demo交易運行中"
        order_status_zh = "候選已選定・執行前風控檢查中"
    elif auto_send and position_count == 0:
        headline_zh = "自動Demo交易運行中・正在掃描市場"
        order_status_zh = "掃描中・尚無新單"
    elif position_count > 0 and protection_active:
        headline_zh = "持倉中・已設置停損與停利"
        order_status_zh = "持倉保護中"
    elif position_count > 0:
        headline_zh = "持倉中"
        order_status_zh = "持倉中・保護確認中"
    else:
        headline_zh = OPS_STATE_ZH[ops_state.value]
        order_status_zh = OPS_STATE_ZH[ops_state.value]

    current_position = None
    if positions:
        p = positions[0]
        current_position = {
            "symbol": p.get("symbol"),
            "side": p.get("side"),
            "size": p.get("size"),
            "entryPrice": p.get("avgPrice") or p.get("entryPrice"),
            "markPrice": p.get("markPrice"),
            "leverage": p.get("leverage"),
            "isolated": True,
            "unrealisedPnl": p.get("unrealisedPnl"),
            "stopLoss": p.get("stopLoss"),
            "takeProfit": p.get("takeProfit"),
            "liquidationPrice": p.get("liqPrice") or p.get("liquidationPrice"),
            "protectionActive": protection_active,
        }

    freshness_ms = scan_age_ms

    # Current block-reason truth: clear stale exposure blockers when exchange is flat + OK.
    controller_health = str(controller.get("controllerHealth") or (
        "HEALTHY" if controller.get("running") else "STOPPED"
    ))
    if controller.get("stalled"):
        controller_health = "STALLED"
    scanner_health = str(controller.get("scannerHealth") or controller_health)

    audit_block_reasons = list(store.last_block_reasons)
    current_block_reasons: list[dict[str, Any]] = []
    for raw in audit_block_reasons:
        reason = str(raw)
        stale = False
        freshness = "unknown"
        truth_match = True
        if reason == "existing_position_or_order":
            if position_count == 0 and open_order_count == 0 and not recovery_required:
                stale = True
                freshness = "stale"
                truth_match = False
            else:
                freshness = "fresh"
        current_block_reasons.append(
            {
                "reason": reason,
                "source": "ops_store.last_block_reasons",
                "observed_at": store.updated_at_ms or store.last_scan_at_ms,
                "source_cycle_id": controller.get("currentCycleId"),
                "freshness": freshness,
                "stale": stale,
                "current_truth_match": truth_match,
            }
        )
    if scanner_health == "STALLED" or controller_health == "STALLED":
        current_block_reasons.append(
            {
                "reason": "scanner_stalled",
                "source": "controller_heartbeat",
                "observed_at": now,
                "source_cycle_id": controller.get("currentCycleId"),
                "freshness": "fresh",
                "stale": False,
                "current_truth_match": True,
            }
        )
    active_block_reasons = [
        b["reason"] for b in current_block_reasons if not b.get("stale")
    ]
    # Keep historical list on store; current API uses active only for blockReasons.
    if (
        position_count == 0
        and open_order_count == 0
        and not recovery_required
        and "existing_position_or_order" in store.last_block_reasons
    ):
        store.last_block_reasons = [
            r for r in store.last_block_reasons if r != "existing_position_or_order"
        ]
        save_ops_store(store)

    status_label = controller_health if controller.get("running") else "STOPPED"

    return {
        "ok": True,
        "mode": "AUTONOMOUS_DEMO",
        "environment": "BYBIT_DEMO",
        "opsState": ops_state.value,
        "opsStateZh": OPS_STATE_ZH[ops_state.value],
        "headlineZh": headline_zh,
        "orderStatusZh": order_status_zh,
        "autoSend": auto_send,
        "autoSendEnv": os.environ.get("NEXUS_AUTONOMOUS_DEMO_AUTO_SEND", "").strip().lower()
        in ("1", "true", "yes"),
        "controllerStatus": status_label,
        "scannerStatus": status_label,
        "controllerHealth": controller_health,
        "scannerHealth": scanner_health,
        "sessionStatus": (
            "ACTIVE"
            if session_pub and session_pub.get("active")
            else (
                "EMERGENCY_STOPPED"
                if session_pub and session_pub.get("emergencyStopped")
                else ("EXPIRED" if session_pub and session_pub.get("expired") else "NONE")
            )
        ),
        "session": session_pub,
        "sessionExpiresAt": (session_pub or {}).get("expiresAtMs"),
        "enabledEnv": autonomous_enabled_from_env(),
        "lastScanAt": store.last_scan_at_ms,
        "lastScanAtMs": store.last_scan_at_ms,
        "lastScanTimeProgressing": scan_progressing,
        "lastCandidateTime": store.last_candidate_at_ms,
        "lastOrderTime": store.last_order_at_ms,
        "lastReflectionTime": store.last_reflection_at_ms,
        "symbolsScanned": store.symbols_scanned,
        "tradableSymbols": store.tradable_symbols,
        "eligibleCandidates": store.eligible_candidates,
        "topCandidate": store.top_candidate,
        "currentPosition": current_position,
        "currentOrder": open_orders[0] if open_orders else None,
        "protectionStatus": "ACTIVE" if protection_active else ("NONE" if position_count == 0 else "UNVERIFIED"),
        "demoEquity": demo_equity,
        "availableBalance": available_balance,
        "dailyPnl": store.daily_pnl,
        "weeklyPnl": store.weekly_pnl,
        "drawdown": store.drawdown,
        "consecutiveLosses": store.consecutive_losses,
        "capitalTier": store.capital_tier,
        "riskTier": store.risk_tier,
        "emergencyStop": bool((session_pub or {}).get("emergencyStopped")),
        "reconciliationStatus": "REQUIRED" if recovery_required else "OK",
        "lastTrade": store.last_trade,
        "lastReflection": store.last_reflection,
        "blockReasons": active_block_reasons,
        "blockReasonsDetail": current_block_reasons,
        "blockReasonsAuditHistory": audit_block_reasons,
        "staleBlockReasonCount": sum(1 for b in current_block_reasons if b.get("stale")),
        "freshness": {
            "lastScanAgeMs": freshness_ms,
            "generatedAtMs": now,
        },
        "runtimeHeartbeat": {
            "boot_id": boot.get("bootId"),
            "commit_sha": deploy_commit,
            "cycle_id": controller.get("currentCycleId"),
            "controller_owner_count": 1 if controller.get("running") else 0,
            "scanner_health": scanner_health,
            "controller_health": controller_health,
            "last_cycle_progress_at": controller.get("lastCycleProgressAtMs"),
            "session_hash": ((session_pub or {}).get("sessionId") or "")[:16],
            "session_state": (
                "ACTIVE"
                if session_pub and session_pub.get("active")
                else "NONE"
            ),
            "position_count": position_count,
            "open_order_count": open_order_count,
            "protection_state": "ACTIVE" if protection_active else "NONE",
            "reconciliation_state": "REQUIRED" if recovery_required else "OK",
            "observed_at": now,
        },
        "lifecycle": {
            "steps": list(LIFECYCLE_STEPS),
            "completed": list(store.lifecycle_completed),
        },
        "controller": controller,
        "controllerOwnerCount": 1 if controller.get("running") else 0,
        "credentialFingerprint": fingerprint[:16] if fingerprint else "",
        "positionCount": position_count,
        "openOrderCount": open_order_count,
        "bootId": boot.get("bootId"),
        "deploymentCommit": deploy_commit,
        "deploymentIdPresent": resolve_deployment_id_present(),
        "commitMatchesHint": deploy_commit[:7] if deploy_commit else "",
        **paper,
        "dryRunDefault": os.environ.get("NEXUS_AUTONOMOUS_DEMO_DRY_RUN", "true"),
        "mainnetAllowed": False,
        "realMoneyAllowed": False,
        "mainnetUsed": False,
        "realMoneyUsed": False,
        "secretSafe": True,
        "accountSnapshotStatus": snap.get("status"),
        "generatedAtMs": now,
    }
