/// Preference model prototype (local/staging only).
class ChannelPreference {
  ChannelPreference({this.enabled = true, this.minPriority = 'NORMAL'});

  bool enabled;
  String minPriority;
}

class NotificationPreferences {
  NotificationPreferences({
    required this.memberId,
    this.pushEnabled = true,
    Map<String, ChannelPreference>? channels,
  }) : channels = channels ??
            {
              for (final k in const [
                'DECISION_STATUS',
                'RISK',
                'DATA_STALE',
                'THESIS_INVALIDATED',
                'MARKET_ANOMALY',
              ])
                k: ChannelPreference(),
            };

  final String memberId;
  bool pushEnabled;
  final Map<String, ChannelPreference> channels;

  bool allows({required String kind, required String priority}) {
    if (!pushEnabled) return false;
    final channel = channels[kind];
    if (channel == null || !channel.enabled) return false;
    const order = ['LOW', 'NORMAL', 'HIGH', 'CRITICAL'];
    return order.indexOf(priority) >= order.indexOf(channel.minPriority);
  }
}
