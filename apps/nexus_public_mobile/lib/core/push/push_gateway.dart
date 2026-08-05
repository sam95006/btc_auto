/// Push notification abstraction — no production credentials in foundation.
abstract class PushGateway {
  Future<void> initialize();
  Future<String?> deviceToken();
  Stream<PushMessage> get messages;
  Future<void> requestPermission();
}

class PushMessage {
  const PushMessage({
    required this.id,
    required this.title,
    required this.body,
    this.deepLink,
    this.category = PushCategory.generic,
  });

  final String id;
  final String title;
  final String body;
  final String? deepLink;
  final PushCategory category;
}

enum PushCategory {
  generic,
  decision,
  risk,
  stale,
  thesis,
  anomaly,
}

/// Local stub used in mock mode and unit tests.
class StubPushGateway implements PushGateway {
  final List<PushMessage> _inbox = [];

  @override
  Future<void> initialize() async {}

  @override
  Future<String?> deviceToken() async => 'stub-device-token';

  @override
  Stream<PushMessage> get messages async* {
    for (final m in _inbox) {
      yield m;
    }
  }

  @override
  Future<void> requestPermission() async {}

  void enqueue(PushMessage message) => _inbox.add(message);
}
