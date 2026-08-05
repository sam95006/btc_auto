import 'package:flutter/material.dart';

import 'core/a11y/a11y_settings.dart';
import 'core/analytics/analytics_consent.dart';
import 'core/crash/crash_reporter.dart';
import 'core/flags/feature_flags.dart';
import 'core/l10n/app_strings.dart';
import 'core/mode/app_mode.dart';
import 'core/theme/nexus_theme.dart';
import 'data/repositories/public_repository.dart';
import 'ui/navigation/app_router.dart';
import 'ui/widgets/demo_banner.dart';

class NexusPublicApp extends StatefulWidget {
  const NexusPublicApp({
    super.key,
    required this.mode,
    required this.flags,
    required this.crashReporter,
  });

  final AppMode mode;
  final FeatureFlagStore flags;
  final CrashReporter crashReporter;

  @override
  State<NexusPublicApp> createState() => _NexusPublicAppState();
}

class _NexusPublicAppState extends State<NexusPublicApp> {
  late final PublicRepository _repository =
      PublicRepository.forMode(widget.mode);
  late final AnalyticsConsentStore _consent = AnalyticsConsentStore();
  late final A11ySettings _a11y = A11ySettings();
  ThemeMode _themeMode = ThemeMode.system;
  Locale _locale = const Locale('en');

  @override
  Widget build(BuildContext context) {
    return NexusScope(
      mode: widget.mode,
      flags: widget.flags,
      repository: _repository,
      consent: _consent,
      a11y: _a11y,
      crashReporter: widget.crashReporter,
      child: MaterialApp(
        title: AppStrings.appName,
        debugShowCheckedModeBanner: false,
        theme: NexusTheme.light(),
        darkTheme: NexusTheme.dark(),
        themeMode: _themeMode,
        locale: _locale,
        supportedLocales: AppStrings.supportedLocales,
        localizationsDelegates: const [
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        builder: (context, child) {
          final media = MediaQuery.of(context);
          return MediaQuery(
            data: media.copyWith(
              textScaler: TextScaler.linear(_a11y.textScale),
              boldText: _a11y.boldText,
            ),
            child: Column(
              children: [
                if (widget.mode.isMock) const DemoBanner(),
                Expanded(child: child ?? const SizedBox.shrink()),
              ],
            ),
          );
        },
        onGenerateRoute: AppRouter.onGenerateRoute,
        initialRoute: AppRouter.home,
        routes: AppRouter.routes(
          onThemeMode: (mode) => setState(() => _themeMode = mode),
          onLocale: (locale) => setState(() => _locale = locale),
        ),
      ),
    );
  }
}

class NexusScope extends InheritedWidget {
  const NexusScope({
    super.key,
    required this.mode,
    required this.flags,
    required this.repository,
    required this.consent,
    required this.a11y,
    required this.crashReporter,
    required super.child,
  });

  final AppMode mode;
  final FeatureFlagStore flags;
  final PublicRepository repository;
  final AnalyticsConsentStore consent;
  final A11ySettings a11y;
  final CrashReporter crashReporter;

  static NexusScope of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<NexusScope>();
    assert(scope != null, 'NexusScope not found');
    return scope!;
  }

  @override
  bool updateShouldNotify(NexusScope oldWidget) {
    return mode != oldWidget.mode ||
        flags != oldWidget.flags ||
        repository != oldWidget.repository;
  }
}
