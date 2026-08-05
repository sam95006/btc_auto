import 'alert_kinds.dart';

/// Stub push client — never talks to APNs/FCM production.
class StubPushClient {
  static const allowedModes = {'STUB', 'MOCK_IN_MEMORY', 'LOCAL_FILE_SINK'};

  final String mode;
  final List<Map<String, Object?>> deliveries = [];

  StubPushClient({this.mode = 'STUB'}) {
    if (!allowedModes.contains(mode)) {
      throw StateError('HARD BAN: push mode "$mode" refused in PUB-K');
    }
  }

  Map<String, Object?> send({
    required Map<String, Object?> alert,
    required String deviceId,
    required String appEnvironment,
  }) {
    if (appEnvironment.toLowerCase() == 'production' ||
        appEnvironment.toLowerCase() == 'prod' ||
        appEnvironment.toLowerCase() == 'live') {
      throw StateError('HARD BAN: production notification credentials refused in PUB-K');
    }
    PrivateFieldDenylist.assertPublic(alert);
    final record = <String, Object?>{
      'status': mode == 'STUB' ? 'STUB_ACCEPTED' : 'MOCK_DELIVERED',
      'device_id': deviceId,
      'alert_id': alert['alert_id'],
      'provider_mode': mode,
      'production_credentials_used': false,
    };
    deliveries.add(record);
    return record;
  }
}
