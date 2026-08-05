/// Offline cache for last-synced public DTOs.
abstract class OfflineCache {
  Future<void> put(String key, Map<String, dynamic> json);
  Future<Map<String, dynamic>?> get(String key);
  Future<void> invalidate(String key);
  Future<void> clear();
}

class MemoryOfflineCache implements OfflineCache {
  final Map<String, Map<String, dynamic>> _entries = {};

  @override
  Future<void> put(String key, Map<String, dynamic> json) async {
    _entries[key] = Map<String, dynamic>.from(json);
  }

  @override
  Future<Map<String, dynamic>?> get(String key) async {
    final value = _entries[key];
    return value == null ? null : Map<String, dynamic>.from(value);
  }

  @override
  Future<void> invalidate(String key) async => _entries.remove(key);

  @override
  Future<void> clear() async => _entries.clear();
}
