import 'package:flutter/material.dart';

import '../../core/l10n/app_strings.dart';

class DemoBanner extends StatelessWidget {
  const DemoBanner({super.key});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Material(
      color: scheme.tertiaryContainer,
      child: SafeArea(
        bottom: false,
        child: Semantics(
          label: 'Demo data banner',
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            child: Row(
              children: [
                Icon(Icons.science_outlined, color: scheme.onTertiaryContainer),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    '${AppStrings.demoData} · ${AppStrings.readOnly} · ${AppStrings.notInvestmentAdvice}',
                    style: Theme.of(context).textTheme.labelMedium?.copyWith(
                          color: scheme.onTertiaryContainer,
                        ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
