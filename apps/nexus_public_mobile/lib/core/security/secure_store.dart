/// Secure storage abstraction — no plugin binding required for foundation.
abstract class SecureStore {
  Future<void> write(String key, String value);
  Future<String?> read(String key);
  Future<void> delete(String key);
  Future<void> clear();
}

/// In-memory secure store for mock / unit tests.
class MemorySecureStore implements SecureStore {
  final Map<String, String> _data = {};

  @override
  Future<void> write(String key, String value) async => _data[key] = value;

  @override
  Future<String?> read(String key) async => _data[key];

  @override
  Future<void> delete(String key) async => _data.remove(key);

  @override
  Future<void> clear() async => _data.clear();
}

/// Biometric unlock abstraction (platform plugin wired later).
abstract class BiometricGate {
  Future<bool> get isAvailable;
  Future<bool> authenticate({required String reason});
}

class NoopBiometricGate implements BiometricGate {
  @override
  Future<bool> get isAvailable async => false;

  @override
  Future<bool> authenticate({required String reason}) async => false;
}
