import 'package:flutter/foundation.dart';

/// Crash reporting abstraction — no vendor SDK required in foundation.
abstract class CrashReporter {
  Future<void> recordError(Object error, StackTrace? stack);
  Future<void> recordFlutterError(FlutterErrorDetails details);
  Future<void> setUserContext(String? anonymizedId);
}

class InMemoryCrashReporter implements CrashReporter {
  final List<String> records = [];

  @override
  Future<void> recordError(Object error, StackTrace? stack) async {
    records.add('error:$error');
  }

  @override
  Future<void> recordFlutterError(FlutterErrorDetails details) async {
    records.add('flutter:${details.exceptionAsString()}');
  }

  @override
  Future<void> setUserContext(String? anonymizedId) async {
    records.add('user:${anonymizedId ?? 'anonymous'}');
  }
}
