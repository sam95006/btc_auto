/// Public alert kind constants (must stay aligned with Python ALERT_KINDS).
class AlertKinds {
  static const decisionStatus = 'DECISION_STATUS';
  static const risk = 'RISK';
  static const dataStale = 'DATA_STALE';
  static const thesisInvalidated = 'THESIS_INVALIDATED';
  static const marketAnomaly = 'MARKET_ANOMALY';

  static const all = <String>{
    decisionStatus,
    risk,
    dataStale,
    thesisInvalidated,
    marketAnomaly,
  };
}

/// Fields refused in any notification / widget payload.
class PrivateFieldDenylist {
  static const fields = <String>{
    'strategy_id',
    'strategy_parameters',
    'private_lesson_id',
    'lesson_id',
    'private_prompt',
    'provider_prompt',
    'order_id',
    'orders',
    'position_id',
    'positions',
    'wallet',
    'wallet_address',
    'account_balance',
    'exchange_credential',
    'api_key',
    'api_secret',
    'execution_route',
    'private_risk_internal',
    'founder_authorization',
    'checkpoint_path',
    'reflection_checkpoint',
    'jwt_private_issuer',
  };

  static void assertPublic(Map<String, Object?> payload) {
    for (final key in payload.keys) {
      final lower = key.toLowerCase();
      if (fields.contains(lower) || fields.any(lower.contains)) {
        throw StateError('HARD BAN: private field "$key" refused in PUB-K payload');
      }
    }
  }
}
