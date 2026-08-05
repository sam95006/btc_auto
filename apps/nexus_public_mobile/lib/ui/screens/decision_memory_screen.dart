import 'package:flutter/material.dart';

import '../../app.dart';
import '../../data/dto/decision_dto.dart';
import '../navigation/app_router.dart';
import '../widgets/common_widgets.dart';

class DecisionMemoryScreen extends StatefulWidget {
  const DecisionMemoryScreen({super.key});

  @override
  State<DecisionMemoryScreen> createState() => _DecisionMemoryScreenState();
}

class _DecisionMemoryScreenState extends State<DecisionMemoryScreen> {
  late Future<List<PublicDecisionSummaryDto>> _future;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future = NexusScope.of(context).repository.decisionMemory();
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
          return const EmptyState(message: 'Decision Memory empty');
        }
        return ListView.builder(
          itemCount: items.length,
          itemBuilder: (context, i) {
            final d = items[i];
            return ListTile(
              title: Text(d.title),
              subtitle: Text(d.thesisHeadline ?? d.symbol ?? d.id),
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
