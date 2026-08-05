import 'package:flutter/material.dart';

import '../../app.dart';
import '../../data/dto/decision_dto.dart';
import '../widgets/common_widgets.dart';

class EvidenceScreen extends StatefulWidget {
  const EvidenceScreen({super.key});

  @override
  State<EvidenceScreen> createState() => _EvidenceScreenState();
}

class _EvidenceScreenState extends State<EvidenceScreen> {
  late Future<List<PublicEvidenceDto>> _future;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future = NexusScope.of(context).repository.evidence();
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<PublicEvidenceDto>>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        final items = snap.data ?? [];
        if (items.isEmpty) {
          return const EmptyState(message: 'No evidence available');
        }
        return ListView.builder(
          itemCount: items.length,
          itemBuilder: (context, i) {
            final e = items[i];
            return ListTile(
              title: Text(e.summary),
              subtitle: Text('${e.source} · ${e.polarity}'),
              trailing: AvailabilityChip(value: e.availability),
            );
          },
        );
      },
    );
  }
}
