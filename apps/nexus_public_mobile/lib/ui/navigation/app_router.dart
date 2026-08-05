import 'package:flutter/material.dart';

import '../../core/l10n/app_strings.dart';
import '../screens/account_screen.dart';
import '../screens/alerts_screen.dart';
import '../screens/decision_detail_screen.dart';
import '../screens/decision_memory_screen.dart';
import '../screens/decisions_screen.dart';
import '../screens/evidence_screen.dart';
import '../screens/home_screen.dart';
import '../screens/markets_screen.dart';
import '../screens/membership_screen.dart';
import '../screens/nex_ai_screen.dart';
import '../screens/notification_settings_screen.dart';
import '../screens/outcome_review_screen.dart';
import '../screens/privacy_screen.dart';
import '../screens/risks_screen.dart';
import '../widgets/app_shell.dart';

class AppRouter {
  static const home = '/';
  static const markets = '/markets';
  static const decisions = '/decisions';
  static const detail = '/decisions/detail';
  static const evidence = '/evidence';
  static const risks = '/risks';
  static const alerts = '/alerts';
  static const memory = '/memory';
  static const outcome = '/outcome';
  static const nexAi = '/nex-ai';
  static const membership = '/membership';
  static const account = '/account';
  static const privacy = '/privacy';
  static const notifications = '/notifications';

  static const shellRoutes = <String>[
    home,
    markets,
    decisions,
    evidence,
    risks,
    alerts,
    memory,
    outcome,
    nexAi,
    membership,
    account,
    privacy,
    notifications,
  ];

  static Map<String, WidgetBuilder> routes({
    required ValueChanged<ThemeMode> onThemeMode,
    required ValueChanged<Locale> onLocale,
  }) {
    return {
      home: (_) => const AppShell(child: HomeScreen()),
      markets: (_) => const AppShell(child: MarketsScreen()),
      decisions: (_) => const AppShell(child: DecisionsScreen()),
      evidence: (_) => const AppShell(child: EvidenceScreen()),
      risks: (_) => const AppShell(child: RisksScreen()),
      alerts: (_) => const AppShell(child: AlertsScreen()),
      memory: (_) => const AppShell(child: DecisionMemoryScreen()),
      outcome: (_) => const AppShell(child: OutcomeReviewScreen()),
      nexAi: (_) => const AppShell(child: NexAiScreen()),
      membership: (_) => const AppShell(child: MembershipScreen()),
      account: (_) => AppShell(
            child: AccountScreen(onThemeMode: onThemeMode, onLocale: onLocale),
          ),
      privacy: (_) => const AppShell(child: PrivacyScreen()),
      notifications: (_) => const AppShell(child: NotificationSettingsScreen()),
    };
  }

  static Route<dynamic>? onGenerateRoute(RouteSettings settings) {
    if (settings.name == detail ||
        (settings.name != null &&
            settings.name!.startsWith('/decisions/') &&
            settings.name != decisions)) {
      final args = settings.arguments;
      final id = args is String
          ? args
          : settings.name!.split('/').where((s) => s.isNotEmpty).last;
      return MaterialPageRoute(
        builder: (_) => AppShell(child: DecisionDetailScreen(decisionId: id)),
        settings: settings,
      );
    }
    return null;
  }

  static String titleFor(String route) {
    switch (route) {
      case home:
        return AppStrings.screenTitle('home');
      case markets:
        return AppStrings.screenTitle('markets');
      case decisions:
        return AppStrings.screenTitle('decisions');
      case detail:
        return AppStrings.screenTitle('detail');
      case evidence:
        return AppStrings.screenTitle('evidence');
      case risks:
        return AppStrings.screenTitle('risks');
      case alerts:
        return AppStrings.screenTitle('alerts');
      case memory:
        return AppStrings.screenTitle('memory');
      case outcome:
        return AppStrings.screenTitle('outcome');
      case nexAi:
        return AppStrings.screenTitle('nex_ai');
      case membership:
        return AppStrings.screenTitle('membership');
      case account:
        return AppStrings.screenTitle('account');
      case privacy:
        return AppStrings.screenTitle('privacy');
      case notifications:
        return AppStrings.screenTitle('notifications');
      default:
        return AppStrings.appName;
    }
  }
}
