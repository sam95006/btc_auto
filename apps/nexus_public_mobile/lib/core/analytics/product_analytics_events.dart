/// PUB2-I product analytics event catalog (Flutter scaffolding).
/// Events are gated behind [AnalyticsConsentStore]; never invent metric values.
library;

import 'analytics_consent.dart';

/// Canonical event names aligned with backend metric schema v1.
abstract final class ProductAnalyticsEvents {
  static const watchlistActivation = 'watchlist_activation';
  static const decisionFirstOpened = 'decision_first_opened';
  static const evidenceEngagement = 'evidence_engagement';
  static const counterEvidenceEngagement = 'counter_evidence_engagement';
  static const taskSuccess = 'task_success';
  static const sessionActive = 'session_active';
  static const decisionReviewCompleted = 'decision_review_completed';
  static const retentionCheckpoint = 'retention_checkpoint';
  static const upgradeIntent = 'upgrade_intent';
  static const validationConversion = 'validation_conversion';

  static const Set<String> catalog = {
    watchlistActivation,
    decisionFirstOpened,
    evidenceEngagement,
    counterEvidenceEngagement,
    taskSuccess,
    sessionActive,
    decisionReviewCompleted,
    retentionCheckpoint,
    upgradeIntent,
    validationConversion,
  };
}

/// Forbidden property keys (PII / secrets) — mirror of backend FORBIDDEN_PROP_KEYS.
abstract final class AnalyticsPrivacyBans {
  static const Set<String> forbiddenPropKeys = {
    'email',
    'e_mail',
    'phone',
    'phone_number',
    'full_name',
    'name',
    'address',
    'ip',
    'ip_address',
    'ssn',
    'password',
    'api_key',
    'api_secret',
    'private_key',
    'access_token',
    'refresh_token',
    'jwt',
    'wallet_address',
    'exchange_api_key',
    'raw_decision_text',
    'lesson_text',
    'prompt_text',
  };
}

/// Consent-aware tracker wrapper that refuses unknown events and PII props.
class ProductAnalyticsClient {
  ProductAnalyticsClient(this._consent, this._sink);

  final AnalyticsConsentStore _consent;
  final AnalyticsSink _sink;

  Future<bool> track(String event, {Map<String, Object?>? props}) async {
    if (!ProductAnalyticsEvents.catalog.contains(event)) {
      return false;
    }
    if (props != null) {
      for (final key in props.keys) {
        if (AnalyticsPrivacyBans.forbiddenPropKeys.contains(key.toLowerCase())) {
          return false;
        }
      }
    }
    if (!_consent.canTrack) {
      return false;
    }
    await _sink.track(event, props: props);
    return true;
  }
}
