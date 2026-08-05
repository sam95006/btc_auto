import 'package:flutter/material.dart';

import '../../app.dart';
import '../../data/dto/decision_dto.dart';
import '../widgets/common_widgets.dart';

class DecisionDetailScreen extends StatefulWidget {
  const DecisionDetailScreen({super.key, required this.decisionId});

  final String decisionId;

  @override
  State<DecisionDetailScreen> createState() => _DecisionDetailScreenState();
}

class _DecisionDetailScreenState extends State<DecisionDetailScreen> {
  late Future<PublicDecisionDetailDto?> _future;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future =
        NexusScope.of(context).repository.decisionDetail(widget.decisionId);
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<PublicDecisionDetailDto?>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        final detail = snap.data;
        if (detail == null) {
          return const EmptyState(message: 'Decision unavailable');
        }
        final s = detail.summary;
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    s.title,
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                ),
                AvailabilityChip(value: s.availability),
              ],
            ),
            const SizedBox(height: 8),
            Text('Posture: ${s.posture}'),
            Text('Confidence: ${s.confidence}'),
            if (s.demo) const Text('DEMO_DATA'),
            const Divider(),
            Text('Context', style: Theme.of(context).textTheme.titleMedium),
            Text(detail.contextNotes),
            const SizedBox(height: 12),
            Text('Human rationale',
                style: Theme.of(context).textTheme.titleMedium),
            Text(detail.humanRationale),
            const SizedBox(height: 12),
            Text('AI assist', style: Theme.of(context).textTheme.titleMedium),
            Text(detail.aiAssistSummary),
            const SizedBox(height: 12),
            Text('Evidence ids: ${detail.evidenceIds.join(', ')}'),
            Text('Risk ids: ${detail.riskIds.join(', ')}'),
          ],
        );
      },
    );
  }
}
