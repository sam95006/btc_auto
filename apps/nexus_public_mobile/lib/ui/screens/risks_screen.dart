import 'package:flutter/material.dart';

import '../../app.dart';
import '../../data/dto/decision_dto.dart';
import '../widgets/common_widgets.dart';

class RisksScreen extends StatefulWidget {
  const RisksScreen({super.key});

  @override
  State<RisksScreen> createState() => _RisksScreenState();
}

class _RisksScreenState extends State<RisksScreen> {
  late Future<List<PublicRiskConditionDto>> _future;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future = NexusScope.of(context).repository.risks();
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<PublicRiskConditionDto>>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        final items = snap.data ?? [];
        if (items.isEmpty) {
          return const EmptyState(message: 'No risk conditions');
        }
        return ListView.builder(
          itemCount: items.length,
          itemBuilder: (context, i) {
            final r = items[i];
            return ListTile(
              title: Text(r.label),
              subtitle: Text(
                '${r.severity}${r.invalidationNote == null ? '' : ' · ${r.invalidationNote}'}',
              ),
              trailing: AvailabilityChip(value: r.availability),
            );
          },
        );
      },
    );
  }
}
