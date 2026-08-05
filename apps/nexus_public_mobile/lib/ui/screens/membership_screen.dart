import 'package:flutter/material.dart';

import '../../app.dart';
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
            const Text(
              'No live billing in this foundation. Entitlements are display-only.',
            ),
          ],
        );
      },
    );
  }
}
