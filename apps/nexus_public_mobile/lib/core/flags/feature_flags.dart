/// Remote-config style feature flags for public mobile.
class FeatureFlagStore {
  FeatureFlagStore(this._flags);

  final Map<String, bool> _flags;

  static const _forbiddenMemberFlags = <String>{
    'auto_trading',
    'copy_trading',
    'exchange_execution',
    'private_strategy',
    'founder_portfolio_access',
    'execution_controls',
    'live_billing',
  };

  factory FeatureFlagStore.defaults() {
    return FeatureFlagStore({
      'nex_ai_chat': true,
      'offline_cache': true,
      'push_alerts': true,
      'biometric_unlock': false,
      'membership_upsell': true,
      'live_streaming': false,
      // PUB17-D: execution / private Founder products stay off.
      'auto_trading': false,
      'copy_trading': false,
      'exchange_execution': false,
      'private_strategy': false,
      'founder_portfolio_access': false,
      'execution_controls': false,
      'live_billing': false,
    });
  }

  bool isEnabled(String key) {
    if (_forbiddenMemberFlags.contains(key)) return false;
    return _flags[key] ?? false;
  }

  void set(String key, bool value) {
    if (_forbiddenMemberFlags.contains(key) && value) {
      throw StateError('HARD BAN: cannot enable forbidden member flag $key');
    }
    _flags[key] = value;
  }

  Map<String, bool> snapshot() => Map<String, bool>.unmodifiable(_flags);
}
