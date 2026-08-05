import 'package:flutter/material.dart';

import '../../app.dart';
import '../../core/push/push_gateway.dart';

class NotificationSettingsScreen extends StatefulWidget {
  const NotificationSettingsScreen({super.key});

  @override
  State<NotificationSettingsScreen> createState() =>
      _NotificationSettingsScreenState();
}

class _NotificationSettingsScreenState
    extends State<NotificationSettingsScreen> {
  final _gateway = StubPushGateway();
  bool _decision = true;
  bool _risk = true;
  bool _stale = true;
  bool _thesis = false;
  bool _anomaly = false;

  @override
  Widget build(BuildContext context) {
    final flags = NexusScope.of(context).flags;
    final pushEnabled = flags.isEnabled('push_alerts');
    return ListView(
      children: [
        SwitchListTile(
          title: const Text('Push alerts master'),
          subtitle: Text(pushEnabled
              ? 'Feature flag enabled (stub gateway)'
              : 'Disabled by feature flag'),
          value: pushEnabled && (_decision || _risk || _stale || _thesis || _anomaly),
          onChanged: pushEnabled
              ? (v) async {
                  if (v) await _gateway.requestPermission();
                  setState(() {
                    _decision = v;
                    _risk = v;
                    _stale = v;
                  });
                }
              : null,
        ),
        SwitchListTile(
          title: const Text('Decision alerts'),
          value: _decision,
          onChanged: pushEnabled ? (v) => setState(() => _decision = v) : null,
        ),
        SwitchListTile(
          title: const Text('Risk alerts'),
          value: _risk,
          onChanged: pushEnabled ? (v) => setState(() => _risk = v) : null,
        ),
        SwitchListTile(
          title: const Text('Stale / freshness'),
          value: _stale,
          onChanged: pushEnabled ? (v) => setState(() => _stale = v) : null,
        ),
        SwitchListTile(
          title: const Text('Thesis monitor'),
          value: _thesis,
          onChanged: pushEnabled ? (v) => setState(() => _thesis = v) : null,
        ),
        SwitchListTile(
          title: const Text('Anomaly'),
          value: _anomaly,
          onChanged: pushEnabled ? (v) => setState(() => _anomaly = v) : null,
        ),
        const ListTile(
          title: Text('Credentials'),
          subtitle: Text(
            'No production push credentials ship in this foundation. Categories map to PushCategory.',
          ),
        ),
      ],
    );
  }
}
