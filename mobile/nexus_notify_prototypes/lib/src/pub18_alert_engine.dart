/// PUB18 Alert Engine — shared read-only contract mirror (mobile).
/// Keep kinds aligned with backend.nexus_pub18_alert_engine.constants / web TS.

class Pub18AlertEngine {
  static const schema = 'pub18_alert_engine_readonly_contract_v1';

  static const opportunityReady = 'OPPORTUNITY_READY';
  static const postureChange = 'POSTURE_CHANGE';
  static const dataTrustDegraded = 'DATA_TRUST_DEGRADED';
  static const regimeTransition = 'REGIME_TRANSITION';
  static const invalidation = 'INVALIDATION';
  static const shadowClosed = 'SHADOW_CLOSED';
  static const providerDegraded = 'PROVIDER_DEGRADED';
  static const marketAnomaly = 'MARKET_ANOMALY';
  static const majorRisk = 'MAJOR_RISK';

  static const kinds = <String>{
    opportunityReady,
    postureChange,
    dataTrustDegraded,
    regimeTransition,
    invalidation,
    shadowClosed,
    providerDegraded,
    marketAnomaly,
    majorRisk,
  };

  /// Required envelope fields: source/as_of/freshness/data_class/decision_id/reason/severity/public_safe (+ kind).
  static const requiredFields = <String>{
    'kind',
    'source',
    'as_of',
    'freshness',
    'data_class',
    'decision_id',
    'reason',
    'severity',
    'public_safe',
  };

  static const hypePhrases = <String>{
    'already ordered',
    'order already filled',
    'filled for you',
    'guaranteed profit',
    'guaranteed return',
    'guaranteed wins',
    'risk-free',
    'risk free',
    'sure win',
    'sure profit',
    'must buy',
    'must sell',
    'buy now',
    'sell now',
    'trade now',
    'copy trade now',
    'auto-execute',
    'auto execute',
    'locked in profit',
    'profit locked',
    'you are in profit',
    'position opened',
    'order placed',
  };

  static void assertPublicSafe(Map<String, Object?> payload) {
    if (payload['public_safe'] != true) {
      throw StateError('HARD BAN: public_safe must be true for PUB18 Alert Engine');
    }
    for (final phrase in hypePhrases) {
      final blob = '${payload['title']} ${payload['body']} ${payload['reason']}'.toLowerCase();
      if (blob.contains(phrase)) {
        throw StateError('HARD BAN: hype phrase refused: $phrase');
      }
    }
  }
}
