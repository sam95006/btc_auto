import 'package:flutter/material.dart';

import '../../app.dart';
import '../../data/dto/decision_dto.dart';
import '../navigation/app_router.dart';
import '../widgets/common_widgets.dart';

class DecisionsScreen extends StatefulWidget {
  const DecisionsScreen({super.key});

  @override
  State<DecisionsScreen> createState() => _DecisionsScreenState();
}

class _DecisionsScreenState extends State<DecisionsScreen> {
  late Future<List<PublicDecisionSummaryDto>> _future;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future = NexusScope.of(context).repository.decisions();
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<PublicDecisionSummaryDto>>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        final items = snap.data ?? [];
        if (items.isEmpty) {
          return const EmptyState(message: 'No decisions available');
        }
        return ListView.builder(
          itemCount: items.length,
          itemBuilder: (context, i) {
            final d = items[i];
            return ListTile(
              title: Text(d.title),
              subtitle: Text('${d.posture} · conf ${d.confidence}'),
              trailing: AvailabilityChip(value: d.availability),
              onTap: () => Navigator.of(context).pushNamed(
                AppRouter.detail,
                arguments: d.id,
              ),
            );
          },
        );
      },
    );
  }
}
