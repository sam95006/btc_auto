import 'package:flutter/material.dart';

import '../../app.dart';
import '../../data/dto/decision_dto.dart';
import '../widgets/common_widgets.dart';

class OutcomeReviewScreen extends StatefulWidget {
  const OutcomeReviewScreen({super.key});

  @override
  State<OutcomeReviewScreen> createState() => _OutcomeReviewScreenState();
}

class _OutcomeReviewScreenState extends State<OutcomeReviewScreen> {
  late Future<List<PublicOutcomeReviewDto>> _future;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future = NexusScope.of(context).repository.outcomeReviews();
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<PublicOutcomeReviewDto>>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        final items = snap.data ?? [];
        if (items.isEmpty) {
          return const EmptyState(message: 'No outcome reviews');
        }
        return ListView.builder(
          itemCount: items.length,
          itemBuilder: (context, i) {
            final o = items[i];
            return ListTile(
              title: Text('${o.processQuality} / ${o.outcomeLabel}'),
              subtitle: Text(o.notes ?? o.decisionId),
              trailing: AvailabilityChip(value: o.availability),
            );
          },
        );
      },
    );
  }
}
