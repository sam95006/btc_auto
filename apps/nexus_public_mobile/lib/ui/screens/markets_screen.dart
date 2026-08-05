import 'package:flutter/material.dart';

import '../../app.dart';
import '../../data/dto/availability.dart';
import '../../data/dto/market_dto.dart';
import '../widgets/common_widgets.dart';

class MarketsScreen extends StatefulWidget {
  const MarketsScreen({super.key});

  @override
  State<MarketsScreen> createState() => _MarketsScreenState();
}

class _MarketsScreenState extends State<MarketsScreen> {
  late Future<PublicMarketOverviewDto> _future;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future = NexusScope.of(context).repository.marketOverview();
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<PublicMarketOverviewDto>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snap.hasError) {
          return EmptyState(message: 'Markets unavailable: ${snap.error}');
        }
        final data = snap.data!;
        return ListView(
          children: [
            ListTile(
              title: Text('As of ${data.asOf.toIso8601String()}'),
              subtitle: Text(data.demo ? 'DEMO_DATA' : 'LIVE'),
              trailing: AvailabilityChip(value: data.availability),
            ),
            for (final s in data.symbols)
              ListTile(
                title: Text(s.symbol),
                subtitle: Text(
                  s.lastPrice == null
                      ? availabilityToWire(s.availability)
                      : '${s.lastPrice} (${s.change24hPct ?? 0}%)',
                ),
                trailing: AvailabilityChip(value: s.availability),
              ),
          ],
        );
      },
    );
  }
}
