import 'package:flutter/material.dart';

import '../../app.dart';
import '../../data/dto/decision_dto.dart';
import '../navigation/app_router.dart';
import '../widgets/common_widgets.dart';

class AlertsScreen extends StatefulWidget {
  const AlertsScreen({super.key});

  @override
  State<AlertsScreen> createState() => _AlertsScreenState();
}

class _AlertsScreenState extends State<AlertsScreen> {
  late Future<List<PublicAlertDto>> _future;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future = NexusScope.of(context).repository.alerts();
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<PublicAlertDto>>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        final items = snap.data ?? [];
        if (items.isEmpty) {
          return const EmptyState(message: 'No alerts');
        }
        return ListView.builder(
          itemCount: items.length,
          itemBuilder: (context, i) {
            final a = items[i];
            return ListTile(
              title: Text(a.title),
              subtitle: Text(a.body ?? a.category),
              trailing: AvailabilityChip(value: a.availability),
              onTap: a.decisionId == null
                  ? null
                  : () => Navigator.of(context).pushNamed(
                        AppRouter.detail,
                        arguments: a.decisionId,
                      ),
            );
          },
        );
      },
    );
  }
}
