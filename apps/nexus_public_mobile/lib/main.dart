import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'app.dart';
import 'core/crash/crash_reporter.dart';
import 'core/flags/feature_flags.dart';
import 'core/mode/app_mode.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final crash = InMemoryCrashReporter();
  FlutterError.onError = (details) {
    crash.recordFlutterError(details);
  };
  final mode = AppMode.fromEnvironment();
  final flags = FeatureFlagStore.defaults();
  runApp(NexusPublicApp(mode: mode, flags: flags, crashReporter: crash));
}
