from __future__ import annotations

from config.daily_report_config import DAILY_REPORT_SLOTS, DAILY_REPORT_TIMEZONE


def _slot_key(now):
    return f"{now.date().isoformat()}_{now.strftime('%H:%M')}"


def should_broadcast(now, last_key):
    slot = now.strftime("%H:%M")
    if slot not in DAILY_REPORT_SLOTS:
        return False, None
    key = _slot_key(now)
    if last_key == key:
        return False, None
    return True, key


def format_report(runtime_store, walk_forward=None, upgrade_status=None):
    from backend.analytics.performance_report import build_performance_report

    perf = build_performance_report(runtime_store)
    walk_forward = walk_forward or {}
    upgrade_status = upgrade_status or {}
    reviews = (upgrade_status.get("learning_reviews") or {}).get("counts") or {}
    lines = [
        f"【NEXUS 戰報】{perf.get('generated_at', '')} ({DAILY_REPORT_TIMEZONE})",
        f"樣本 {perf.get('sample_size', 0)} 筆｜勝率 {float(perf.get('win_rate', 0) or 0)*100:.1f}%｜累計 {perf.get('total_pnl', 0):.2f}U",
        f"Profit factor {perf.get('profit_factor', 0):.2f}｜最大回撤 {perf.get('max_drawdown', 0):.2f}U",
    ]
    if walk_forward.get("ready"):
        lines.append(
            f"Walk-forward 正窗口比 {float(walk_forward.get('positive_window_ratio', 0) or 0)*100:.1f}%"
        )
    rotation = upgrade_status.get("rotation") or {}
    if rotation.get("recommendation"):
        lines.append(f"策略建議：{rotation.get('recommendation')}（{rotation.get('reason', '')}）")
    if reviews:
        lines.append(f"學習審核：{reviews}")
    lines.append("BTC/ETH/SOL/PEPE 由固定艦隊操作；動態選幣僅 RADAR 哨站。")
    return "\n".join(lines)
