import 'alert_kinds.dart';

/// Widget / Live Activity snapshot prototypes (no platform SDK calls).
class WidgetSnapshot {
  WidgetSnapshot({
    required this.widgetKind,
    required this.headline,
    required this.subtitle,
    required this.statusChip,
    required this.deepLink,
    required this.asOf,
    required this.freshness,
    required this.mode,
    this.fields = const {},
  });

  final String widgetKind;
  final String headline;
  final String subtitle;
  final String statusChip;
  final String deepLink;
  final String asOf;
  final String freshness;
  final String mode;
  final Map<String, Object?> fields;

  Map<String, Object?> toJson() {
    final payload = <String, Object?>{
      'widget_kind': widgetKind,
      'headline': headline,
      'subtitle': subtitle,
      'status_chip': statusChip,
      'deep_link': deepLink,
      'as_of': asOf,
      'freshness': freshness,
      'mode': mode,
      'fields': fields,
    };
    PrivateFieldDenylist.assertPublic(payload);
    PrivateFieldDenylist.assertPublic(Map<String, Object?>.from(fields));
    return payload;
  }
}

class IOSLiveActivityPrototype {
  Map<String, Object?> start(WidgetSnapshot snapshot) => {
        'action': 'START',
        'platform': 'ios',
        'snapshot': snapshot.toJson(),
        'production_push_token_used': false,
        'note': 'prototype only; ActivityKit not invoked',
      };
}

class AndroidWidgetPrototype {
  Map<String, Object?> render(WidgetSnapshot snapshot) => {
        'platform': 'android',
        'remote_views': snapshot.toJson(),
        'note': 'prototype only; AppWidgetManager not invoked',
      };
}
