import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Dart-side hard-ban scan over the public mobile lib tree.
/// Forbidden tokens are assembled at runtime so this file itself is clean.
void main() {
  test('lib tree contains no banned exchange/trading/private markers', () {
    final root = Directory('lib');
    expect(root.existsSync(), isTrue);
    final banned = <RegExp>[
      RegExp(['by', 'bit'].join(), caseSensitive: false),
      RegExp(['bin', 'ance'].join(), caseSensitive: false),
      RegExp(['ok', 'x'].join(), caseSensitive: false),
      RegExp(['private', r'[_-]?', 'core'].join(), caseSensitive: false),
      RegExp(['place', '_', 'order'].join(), caseSensitive: false),
      RegExp(['create', '_', 'order'].join(), caseSensitive: false),
      RegExp(['wallet', '_', 'address'].join(), caseSensitive: false),
      RegExp(['api', '_', 'secret'].join(), caseSensitive: false),
      RegExp(['exchange', '_', 'api'].join(), caseSensitive: false),
    ];
    final violations = <String>[];
    for (final entity in root.listSync(recursive: true)) {
      if (entity is! File || !entity.path.endsWith('.dart')) continue;
      final text = entity.readAsStringSync();
      for (final re in banned) {
        if (re.hasMatch(text)) {
          violations.add('${entity.path} ~ ${re.pattern}');
        }
      }
    }
    expect(violations, isEmpty, reason: violations.join('\n'));
  });
}
