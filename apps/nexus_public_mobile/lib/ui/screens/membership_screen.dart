import 'package:flutter/material.dart';

import '../../app.dart';
import '../../core/subscription/subscription_boundary.dart';
import '../../data/dto/decision_dto.dart';
import '../widgets/common_widgets.dart';

class MembershipScreen extends StatefulWidget {
  const MembershipScreen({super.key});

  @override
  State<MembershipScreen> createState() => _MembershipScreenState();
}

class _MembershipScreenState extends State<MembershipScreen> {
  late Future<PublicMembershipDto> _future;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future = NexusScope.of(context).repository.membership();
  }

  @override
  Widget build(BuildContext context) {
    final boundary = subscriptionBoundarySnapshot();
    final buyable = (boundary['buyable'] as Map<String, String>);
    final notForSale = (boundary['not_for_sale'] as Map<String, String>);

    return FutureBuilder<PublicMembershipDto>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snap.hasError) {
          return EmptyState(message: '${snap.error}');
        }
        final m = snap.data!;
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text('Tier: ${m.tier}',
                style: Theme.of(context).textTheme.titleLarge),
            Text('Status: ${m.status}'),
            if (m.renewalLabel != null) Text(m.renewalLabel!),
            const SizedBox(height: 16),
            Text('Members may buy',
                style: Theme.of(context).textTheme.titleMedium),
            for (final e in buyable.entries) Text('• ${e.value}'),
            const SizedBox(height: 12),
            Text('Members do not buy',
                style: Theme.of(context).textTheme.titleMedium),
            for (final e in notForSale.entries) Text('• ${e.value}'),
            const SizedBox(height: 16),
            const Text(
              'No live billing. member_execution_control_count = 0. '
              'Entitlements never grant Auto Trading, Copy Trading, '
              'Exchange Execution, Private Strategy, or Founder Portfolio Access.',
            ),
          ],
        );
      },
    );
  }
}
