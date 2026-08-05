/// Analytics events are gated behind explicit consent.
enum ConsentState { unknown, granted, denied }

class AnalyticsConsentStore {
  ConsentState state = ConsentState.unknown;

  bool get canTrack => state == ConsentState.granted;

  void grant() => state = ConsentState.granted;
  void deny() => state = ConsentState.denied;
}

abstract class AnalyticsSink {
  Future<void> track(String event, {Map<String, Object?>? props});
}

class ConsentAwareAnalytics implements AnalyticsSink {
  ConsentAwareAnalytics(this._consent, this._inner);

  final AnalyticsConsentStore _consent;
  final AnalyticsSink _inner;

  @override
  Future<void> track(String event, {Map<String, Object?>? props}) async {
    if (!_consent.canTrack) return;
    await _inner.track(event, props: props);
  }
}

class MemoryAnalyticsSink implements AnalyticsSink {
  final List<Map<String, Object?>> events = [];

  @override
  Future<void> track(String event, {Map<String, Object?>? props}) async {
    events.add({'event': event, ...?props});
  }
}
