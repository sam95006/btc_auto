/// Localization foundation (ARB-ready). Hand-maintained strings until
/// `flutter gen-l10n` is available on the host toolchain.
/// Default product locale: zh-TW. English is fully ready.
import 'package:flutter/material.dart';

class AppStrings {
  AppStrings._();

  static const appName = 'NEXUS';
  static const demoData = 'DEMO_DATA';
  static const notInvestmentAdvice = 'Not investment advice';
  static const readOnly = 'Read-only Decision Integrity';

  /// Product default — Traditional Chinese (Taiwan).
  static const Locale defaultLocale = Locale('zh', 'TW');

  static const supportedLocales = <Locale>[
    Locale('zh', 'TW'),
    Locale('en'),
  ];

  static String screenTitle(String route, {Locale? locale}) {
    final code = _code(locale);
    final zh = <String, String>{
      'home': '首頁',
      'markets': '市場',
      'decisions': '決策',
      'detail': '決策詳情',
      'evidence': '證據',
      'counter': '反證',
      'risks': '風險條件',
      'alerts': '警示',
      'memory': '決策記憶',
      'outcome': '結果回顧',
      'nex_ai': 'NEX AI',
      'membership': '會員',
      'account': '帳戶',
      'privacy': '隱私',
      'notifications': '通知設定',
    };
    final en = <String, String>{
      'home': 'Home',
      'markets': 'Markets',
      'decisions': 'Decisions',
      'detail': 'Decision Detail',
      'evidence': 'Evidence',
      'counter': 'Counter Evidence',
      'risks': 'Risks',
      'alerts': 'Alerts',
      'memory': 'Decision Memory',
      'outcome': 'Outcome Review',
      'nex_ai': 'NEX AI',
      'membership': 'Membership',
      'account': 'Account',
      'privacy': 'Privacy',
      'notifications': 'Notification Settings',
    };
    final table = code == 'en' ? en : zh;
    return table[route] ?? appName;
  }

  static String _code(Locale? locale) {
    if (locale == null) return 'zh_TW';
    if (locale.languageCode == 'en') return 'en';
    return 'zh_TW';
  }
}
