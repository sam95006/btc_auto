import 'package:flutter/material.dart';

import '../../app.dart';
import '../navigation/app_router.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final mode = NexusScope.of(context).mode;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(
          'Decision Integrity',
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        const SizedBox(height: 8),
        Text(
          'Public-safe Decision Intelligence. Mode: ${mode.name}.',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        const SizedBox(height: 16),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            _LinkChip('Markets', AppRouter.markets),
            _LinkChip('Decisions', AppRouter.decisions),
            _LinkChip('Evidence', AppRouter.evidence),
            _LinkChip('Risks', AppRouter.risks),
            _LinkChip('Alerts', AppRouter.alerts),
            _LinkChip('Memory', AppRouter.memory),
            _LinkChip('Outcomes', AppRouter.outcome),
            _LinkChip('NEX AI', AppRouter.nexAi),
            _LinkChip('Membership', AppRouter.membership),
          ],
        ),
      ],
    );
  }
}

class _LinkChip extends StatelessWidget {
  const _LinkChip(this.label, this.route);
  final String label;
  final String route;

  @override
  Widget build(BuildContext context) {
    return ActionChip(
      label: Text(label),
      onPressed: () => Navigator.of(context).pushReplacementNamed(route),
    );
  }
}
