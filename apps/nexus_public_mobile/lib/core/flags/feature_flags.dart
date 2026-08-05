/// Remote-config style feature flags for public mobile.
class FeatureFlagStore {
  FeatureFlagStore(this._flags);

  final Map<String, bool> _flags;

  factory FeatureFlagStore.defaults() {
    return FeatureFlagStore({
      'nex_ai_chat': true,
      'offline_cache': true,
      'push_alerts': true,
      'biometric_unlock': false,
      'membership_upsell': true,
      'live_streaming': false,
    });
  }

  bool isEnabled(String key) => _flags[key] ?? false;

  void set(String key, bool value) => _flags[key] = value;

  Map<String, bool> snapshot() => Map<String, bool>.unmodifiable(_flags);
}
