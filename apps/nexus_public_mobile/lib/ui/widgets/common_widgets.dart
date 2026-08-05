import 'package:flutter/material.dart';

import '../../data/dto/availability.dart';

class AvailabilityChip extends StatelessWidget {
  const AvailabilityChip({super.key, required this.value});

  final Availability value;

  @override
  Widget build(BuildContext context) {
    final label = availabilityToWire(value);
    return Semantics(
      label: 'Availability $label',
      child: Chip(
        label: Text(label),
        visualDensity: VisualDensity.compact,
      ),
    );
  }
}

class EmptyState extends StatelessWidget {
  const EmptyState({super.key, required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Text(message, textAlign: TextAlign.center),
      ),
    );
  }
}
