from collections import defaultdict
from datetime import datetime
from uuid import uuid4


REJECT_REASON_LABELS = {
    "no_high_quality_context": "?®å?æ²’æ?é«˜å?è³ªé€²å ´?°å?",
    "adjusted_confidence_below_threshold": "?¡æ?å¾Œä¿¡å¿ƒå??¸ä?è¶?,
    "funding_warning": "è³‡é?è²»ç??²å…¥è­¦å??€",
    "similar_loss_pattern": "è¨Šè??Œè??Ÿè™§?å??‹é??¼ç›¸ä¼?,
    "pepe_margin_above_btc_cap": "PEPE ä¿è??‘è???BTC å®‰å…¨ä¸Šé?",
    "market_context_blocked": "å¸‚å ´?¶åº¦ä¸æ”¯?é€™å€‹æ–¹??,
    "quality_score_below_threshold": "?²å ´?è³ª?†æ•¸å¤ªä?",
    "direction_cooldown_active": "?Œæ–¹?‘å????å¤±æ?ï¼Œä??¨å†·?»æ???,
    "strategy_regime_paused": "è©²ç??¥åœ¨?®å?å¸‚å ´?¶åº¦å·²æš«??,
    "fleet_paused_due_to_low_score": "?¦é?è©•å?å¤ªä?ï¼Œæš«?œæ–°??,
    "btc_reverse_pressure": "BTC ?å?å£“å?å¤ªå¼·",
    "high_volatility": "æ³¢å??é?",
    "low_volume": "?äº¤?ä?è¶?,
    "poor_risk_reward": "é¢¨éšª?±é…¬æ¯”ä?è¶?,
}


class RoundTableMeetingEngine:
    PARTICIPANTS = [
        ("HQ", "ç¸½éƒ¨?‡æ®å®?),
        ("HQ", "ç¸½éƒ¨äº‹ä»¶çµ±æ•´??),
        ("HQ", "ç¸½éƒ¨ç¸½é?è¡Œå?"),
        ("LEDGER", "ç¸½éƒ¨è³‡é?ç¸½å¸³å®?),
        ("LEDGER", "ç¸½éƒ¨?Ÿè²¸å®?),
        ("LEDGER", "ç¸½éƒ¨?¦é?èª¿åº¦å®?),
        ("HQ", "ç¸½éƒ¨æ±ºç?å¯©è?å®?),
        ("WHALE", "å·¨é¯¨??§??),
        ("FUNDING", "è³‡é?è²»ç???§??),
        ("RADAR", "è­¦å ±å®?),
        ("NEWS", "?°è??é???),
        ("NEWS", "?°è??†æ?å¸?),
        ("MARKET", "å¸‚åƒ¹è³‡æ???),
        ("MARKET", "å¸‚å ´?…å??†æ???),
        ("BTC", "BTC ?¦é???),
        ("ETH", "ETH ?¦é???),
        ("SOL", "SOL ?¦é???),
        ("PEPE", "PEPE ?¦é???),
        ("HQ", "è¨Šè??å??†æ?å¸?),
        ("HQ", "?²å ´?è³ªå¯©æ ¸å®?),
        ("HQ", "è¨Šè?è¨˜æ†¶å®?),
        ("HQ", "ä¿¡å??¡æ?å®?),
        ("HQ", "setup ?†é?å®?),
        ("HQ", "?¦é?è©•å?å®?),
        ("RISK", "è·¨è‰¦?Šç›¸?œæ€§é¢¨?§å?"),
        ("RISK", "é¢¨æ§å®?),
        ("HQ", "æ¨¡æ“¬äº¤æ???),
        ("HQ", "?å€‰å?"),
        ("HQ", "PnL å®?),
        ("RISK", "?ºå ´æª¢è?å®?),
    ]

    def create_meeting(self, meeting_type, snapshot, reason=""):
        meeting_id = f"mtg_{uuid4().hex[:12]}"
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        participants = [{"station": station, "speaker": speaker} for station, speaker in self.PARTICIPANTS]
        unit_reports = self._build_unit_reports(snapshot, reason)
        discussion_messages = self._build_discussion_messages(unit_reports, meeting_type)
        conclusion = self._build_conclusion(snapshot, unit_reports, meeting_type, reason)
        return {
            "meeting_id": meeting_id,
            "time": created_at,
            "created_at": created_at,
            "type": meeting_type,
            "participants": participants,
            "unit_reports": unit_reports,
            "discussion_messages": discussion_messages,
            "conclusion": conclusion,
            "broadcasted": False,
            "summary": conclusion.get("summary", ""),
        }

    def _build_unit_reports(self, snapshot, reason):
        reports = defaultdict(list)
        system = snapshot.get("system", {})
        capital = snapshot.get("capital", {})
        pnl = snapshot.get("pnl", {})
        news = snapshot.get("news", [])
        whale = snapshot.get("whale", {})
        funding = snapshot.get("funding", {})
        audits = snapshot.get("decision_audit", [])

        reports["HQ"].append({"speaker": "ç¸½éƒ¨?‡æ®å®?, "message": f"?®å?è­¦å ±ç­‰ç???{system.get('alert_level', 'NORMAL')}ï¼Œäº¤?“æš«?œç??‹ç‚º {system.get('trading_paused', False)}??})
        reports["HQ"].append({"speaker": "ç¸½éƒ¨äº‹ä»¶çµ±æ•´??, "message": f"?€è¿‘ä?ä»¶æ•¸ {len(snapshot.get('events', []))}ï¼Œæ?è¿‘æ?è­°æ•¸ {len(snapshot.get('meetings', []))}??})
        reports["HQ"].append({"speaker": "ç¸½éƒ¨ç¸½é?è¡Œå?", "message": f"?¬è¼ª?‹è??¥åº·?€??{system.get('system_health', 'ONLINE')}ï¼Œè§¸?¼å?? ï?{reason or 'ä¾‹è??ƒè­°'}??})
        reports["HQ"].append({"speaker": "ç¸½éƒ¨æ±ºç?å¯©è?å®?, "message": f"?€è¿‘å¯©è¨ˆæ¨£??{len(audits)} ç­†ï?ä¸»è??’å–®?Ÿå?å·²ç??¥æœ¬æ¬¡æ?è­°ã€?})

        reports["LEDGER"].append({"speaker": "ç¸½éƒ¨è³‡é?ç¸½å¸³å®?, "message": f"ç¸½è???{capital.get('total', 0):.2f}Uï¼ŒHQ æº–å???{capital.get('hq_reserve', 0):.2f}U??})
        reports["LEDGER"].append({"speaker": "ç¸½éƒ¨?Ÿè²¸å®?, "message": f"?®å??Ÿæ¬¾ç¸½é? {sum(item.get('principal', 0.0) for item in snapshot.get('loans', {}).values()):.2f}U??})
        reports["LEDGER"].append({"speaker": "ç¸½éƒ¨?¦é?èª¿åº¦å®?, "message": "?„è‰¦?Šå¯ä¾æœ¬æ¬¡æ?è­°èª¿?´æ³¨?ä??…è?æ¬Šé?ï¼Œä?ä¸ç›´?¥ä??®ã€?})

        reports["WHALE"].append({"speaker": "å·¨é¯¨??§??, "message": f"å·¨é¯¨?€??{whale.get('severity', 'NORMAL')}ï¼Œé?é»ï?{whale.get('summary', 'å·¨é¯¨æ¨¡æ“¬??§?‹è?ä¸­ã€?)}??})
        reports["FUNDING"].append({"speaker": "è³‡é?è²»ç???§??, "message": f"Funding ?€??{funding.get('severity', 'NORMAL')}ï¼Œé?é»ï?{funding.get('summary', 'è³‡é?è²»ç?æ¨¡æ“¬??§?‹è?ä¸­ã€?)}??})
        reports["RADAR"].append({"speaker": "è­¦å ±å®?, "message": f"?·é?ç«™å»ºè­°ç¶­??{system.get('alert_level', 'NORMAL')} è­¦æ???})

        categories = sorted({item.get("category", "ç¶œå?") for item in news})
        reports["NEWS"].append({"speaker": "?°è??é???, "message": f"å·²æ”¶?†æ–°??{len(news)} ?‡ï?æ¬„ä?æ¶µè?ï¼š{'??.join(categories) if categories else 'ç¶œå?'}??})
        reports["NEWS"].append({"speaker": "?°è??†æ?å¸?, "message": f"?€?°æ–°?é?é»ï?{news[0].get('summary', '?®å?æ²’æ??°ç??å¤§?°è???) if news else '?®å?æ²’æ??°ç??å¤§?°è???}"})

        reports["MARKET"].append({"speaker": "å¸‚åƒ¹è³‡æ???, "message": f"?®å?è¿½è¹¤?¹æ ¼æ¨™ç?ï¼š{', '.join(snapshot.get('prices', {}).keys()) or 'BTC, ETH, SOL, PEPE'}??})
        reports["MARKET"].append({"speaker": "å¸‚å ´?…å??†æ???, "message": "å¸‚å ´?¶åº¦?æ³¢?•ã€æ”¯?é˜»?›è??‡ç??´é¢¨?ªå·²?é??°å??¦é??²å ´å¯©æ ¸??})

        for fleet in ["BTC", "ETH", "SOL", "PEPE"]:
            fleet_state = system.get("fleet_status", {}).get(fleet, {})
            fleet_pnl = pnl.get("fleets", {}).get(fleet, {})
            reports[fleet].append(
                {
                    "speaker": f"{fleet} ?¦é???,
                    "message": f"?¶å??€??{fleet_state.get('status', 'STANDBY')}ï¼Œæ?è¿‘è???{fleet_state.get('last_signal', 'HOLD')}ï¼Œç¸½?ç? {fleet_pnl.get('total', 0):.2f}U??,
                }
            )

        return dict(reports)

    def _build_discussion_messages(self, unit_reports, meeting_type):
        messages = []
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for station, rows in unit_reports.items():
            for row in rows[:2]:
                messages.append(
                    {
                        "timestamp": timestamp,
                        "station": station,
                        "speaker": row["speaker"],
                        "message": row["message"],
                        "source": meeting_type,
                        "importance": "HIGH" if station in ("HQ", "RISK", "RADAR") else "INFO",
                    }
                )
        return messages[:40]

    def _build_conclusion(self, snapshot, unit_reports, meeting_type, reason):
        alert_level = snapshot.get("system", {}).get("alert_level", "NORMAL")
        audits = snapshot.get("decision_audit", [])
        reject_counts = defaultdict(int)
        for item in audits[:60]:
            if item.get("reject_reason"):
                reject_counts[item["reject_reason"]] += 1
        top_rejects = [key for key, _ in sorted(reject_counts.items(), key=lambda item: item[1], reverse=True)[:5]]
        top_reject_labels = [REJECT_REASON_LABELS.get(code, code) for code in top_rejects]

        fleet_instructions = {}
        station_instructions = {}
        forbidden_actions = defaultdict(list)
        watchlist = defaultdict(list)
        risk_notes = defaultdict(list)

        for fleet in ["BTC", "ETH", "SOL", "PEPE"]:
            fleet_state = snapshot.get("system", {}).get("fleet_status", {}).get(fleet, {})
            fleet_instructions[fleet] = [
                f"?€è¿‘è??Ÿç‚º {fleet_state.get('last_signal', 'HOLD')}ï¼Œå??µå??è³ª?†æ•¸?‡ç›¸?œæ€§é¢¨?§ã€?,
                "?¥æ?è¿‘é€???’å–®å¢å?ï¼Œå„ª?ˆæª¢?¥å??´åˆ¶åº¦è??äº¤?æ”¯?ã€?,
            ]
            watchlist[fleet] = [fleet, "BTC èµ°å‹¢", "Funding ?€??]

        station_instructions["HQ"] = ["ä¾æœ¬æ¬¡å?æ¡Œæ?è­°ç?è«–å?æ­¥æ??‰ç??°è??¶ã€?, "?ƒè­°ä¸å??´æ¥ä¸‹å–®ï¼Œåª?½èª¿?´æ³¨?ä??…è?æ¬Šé???]
        station_instructions["RADAR"] = ["?ç???§å·¨é¯¨??funding ?°å¸¸ï¼Œè‹¥?‡ç?ç«‹å³å»?’­??]
        station_instructions["NEWS"] = ["?ç??´æ–°?¯æ??ƒã€ç??‹è²¡?‘è‚¡å¸‚ã€å?å¯†é?å¤§è?è¨Šã€ç??‹æ”¿åºœè?è¨Šè?ä¸–ç?è²¡é?è³‡è???]
        station_instructions["WHALE"] = ["å·¨é¯¨?°å¸¸?‚å„ª?ˆé€šçŸ¥ HQ ?‡å??‰è‰¦?Šã€?]
        station_instructions["FUNDING"] = ["Funding ?‡ç? WARNING ?‚å„ª?ˆæ???RISK ??HQ??]
        station_instructions["RISK"] = ["?¥æ??®å?? é?ä¸­æ–¼?¸é??§æ?é«˜æ³¢?•ï?ä¸‹ä?è¼ªå??é??¶ã€?]
        station_instructions["MARKET"] = ["ç¶­æ?å¸‚å ´?¶åº¦?æ”¯?é˜»?›è??‡ç??´é¢¨?ªåˆ¤?·ã€?]
        station_instructions["LEDGER"] = ["ç¶­æ?è³‡é??‡å€Ÿæ¬¾å£“å???§ï¼Œåª?é??¢æ?æµç?èª¿æ•´æ¬Šé???]

        if alert_level != "NORMAL":
            forbidden_actions["ALL"].append("è­¦å ±?ªè§£?¤å?ï¼Œä?å¾—æ–°å¢é?é¢¨éšª?¹å??„æ–°?®ã€?)
            risk_notes["RISK"].append("?®å?ç³»çµ±ä»åœ¨è­¦æ??€?‹ï??€?‰é?æ§“æ¡¿ç­–ç•¥ç¶­æ??åˆ¶??)

        if "btc_reverse_pressure" in top_rejects:
            forbidden_actions["PEPE"].append("BTC å£“åˆ¶ altcoin ?‚ï?ç¦æ­¢ PEPE ?†å‹¢?šå???)
            forbidden_actions["SOL"].append("BTC å£“åˆ¶ altcoin ?‚ï?SOL ä¸å??†å‹¢?¾å¤§?‰ä???)
        if "high_volatility" in top_rejects:
            forbidden_actions["ALL"].append("æ³¢å??é??‚ï?ä¸è?è¿½åƒ¹?‡ç¡¬?šç??´ã€?)
            risk_notes["RISK"].append("è¿‘æ?é«˜æ³¢?•æ??®å?å¤šï?ä¸‹ä?è¼ªå„ª?ˆé?ä½é€²å ´?Ÿåº¦??)

        watchlist["NEWS"] = ["?¯æ???, "ç¾å?è²¡é??¡å?", "? å?è²¨å¹£?å¤§è³‡è?", "ç¾å??¿å?è³‡è?", "ä¸–ç?è²¡é?è³‡è?"]
        watchlist["RADAR"] = ["å·¨é¯¨æµå?", "Funding æ¥µç«¯??, "å¸‚å ´?Œæ­¥?°å?"]
        watchlist["HQ"] = ["ä¸»è??’å–®?Ÿå?", "?„è‰¦?Šå???, "ç¸½è??‘é¢¨??]

        prefix = "ç·Šæ€? if meeting_type == "EMERGENCY_ROUND_TABLE" else "ä¾‹è?"
        summary = f"{prefix}?“æ??ƒè­°å®Œæ?ï¼Œé?é»æ??®å?? ï?{'??.join(top_reject_labels) if top_reject_labels else '?®å?æ²’æ??é¡¯?†ä¸­?’å–®?Ÿå?'}??
        if reason:
            summary += f" è§¸ç™¼?Ÿå?ï¼š{reason}??

        return {
            "summary": summary,
            "next_6h_focus": [
                "?ªå??·è?é«˜å?è³?setupï¼Œé¿?ä??è¿½?¹ã€?,
                "?ç???§ BTC å°?altcoin ?„å??¶æ??œã€?,
                "ä»»ä?è­¦å ±?‡ç??½é??ˆå?æ­?HQ?RISK?RADAR??,
            ],
            "fleet_instructions": fleet_instructions,
            "station_instructions": station_instructions,
            "forbidden_actions": dict(forbidden_actions),
            "watchlist": dict(watchlist),
            "risk_notes": dict(risk_notes),
        }
