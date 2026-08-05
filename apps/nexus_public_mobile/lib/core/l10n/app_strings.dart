import 'package:flutter/material.dart';

/// Localization foundation (ARB-ready). Hand-maintained strings until
/// `flutter gen-l10n` is available on the host toolchain.
class AppStrings {
  static const appName = 'NEXUS';
  static const demoData = 'DEMO_DATA';
  static const notInvestmentAdvice = 'Not investment advice';
  static const readOnly = 'Read-only Decision Intelligence';

  static const supportedLocales = <Locale>[
    Locale('en'),
    Locale('zh', 'TW'),
  ];

  static String screenTitle(String route) {
    switch (route) {
      case 'home':
        return 'Home';
      case 'markets':
        return 'Markets';
      case 'decisions':
        return 'Decisions';
      case 'detail':
        return 'Decision Detail';
      case 'evidence':
        return 'Evidence';
      case 'risks':
        return 'Risks';
      case 'alerts':
        return 'Alerts';
      case 'memory':
        return 'Decision Memory';
      case 'outcome':
        return 'Outcome Review';
      case 'nex_ai':
        return 'NEX AI';
      case 'membership':
        return 'Membership';
      case 'account':
        return 'Account';
      case 'privacy':
        return 'Privacy';
      case 'notifications':
        return 'Notification Settings';
      default:
        return appName;
    }
  }
}
