from datetime import datetime


class EmergencyMeetingTrigger:
    def __init__(self, state_manager, event_bus):
        self.state_manager = state_manager
        self.event_bus = event_bus

    def trigger(self, reason):
        self.state_manager.set_alert("ALERT_RED", emergency=True, trading_paused=True)
        meeting = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": "EMERGENCY",
            "summary": f"ç·Šæ€¥æ?è­°å??•ï?{reason}?‚æš«?œæ??‰æ–°?„æ¨¡?¬ä??®ã€?,
        }
        self.event_bus.publish("emergency_meeting_triggered", meeting)
        return meeting
