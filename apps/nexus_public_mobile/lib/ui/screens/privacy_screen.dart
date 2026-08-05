import 'package:flutter/material.dart';

import '../../app.dart';
import '../../core/analytics/analytics_consent.dart';

class PrivacyScreen extends StatelessWidget {
  const PrivacyScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final consent = NexusScope.of(context).consent;
    return StatefulBuilder(
      builder: (context, setState) {
        return ListView(
          children: [
            const ListTile(
              title: Text('Privacy foundation'),
              subtitle: Text(
                'Analytics require explicit consent. Crash reports are anonymized abstractions.',
              ),
            ),
            RadioListTile<ConsentState>(
              title: const Text('Analytics: unknown'),
              value: ConsentState.unknown,
              groupValue: consent.state,
              onChanged: (_) => setState(() => consent.state = ConsentState.unknown),
            ),
            RadioListTile<ConsentState>(
              title: const Text('Analytics: granted'),
              value: ConsentState.granted,
              groupValue: consent.state,
              onChanged: (_) => setState(consent.grant),
            ),
            RadioListTile<ConsentState>(
              title: const Text('Analytics: denied'),
              value: ConsentState.denied,
              groupValue: consent.state,
              onChanged: (_) => setState(consent.deny),
            ),
            const ListTile(
              title: Text('Data export / deletion'),
              subtitle: Text(
                'Account deletion and export are handled by the public auth membership service (PUB-H). This screen only surfaces the entry point.',
              ),
            ),
          ],
        );
      },
    );
  }
}
