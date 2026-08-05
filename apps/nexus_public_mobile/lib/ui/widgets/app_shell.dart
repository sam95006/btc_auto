import 'package:flutter/material.dart';

import '../navigation/app_router.dart';

class AppShell extends StatelessWidget {
  const AppShell({super.key, required this.child});

  final Widget child;

  static const _destinations = <_NavDest>[
    _NavDest(AppRouter.home, Icons.home_outlined, Icons.home, 'Home'),
    _NavDest(AppRouter.markets, Icons.show_chart_outlined, Icons.show_chart, 'Markets'),
    _NavDest(AppRouter.decisions, Icons.account_tree_outlined, Icons.account_tree, 'Decisions'),
    _NavDest(AppRouter.alerts, Icons.notifications_outlined, Icons.notifications, 'Alerts'),
    _NavDest(AppRouter.account, Icons.person_outline, Icons.person, 'Account'),
  ];

  @override
  Widget build(BuildContext context) {
    final route = ModalRoute.of(context)?.settings.name ?? AppRouter.home;
    final selected = _destinations.indexWhere((d) => d.route == route);
    final index = selected < 0 ? 0 : selected;

    return Scaffold(
      appBar: AppBar(
        title: Text(AppRouter.titleFor(route)),
        actions: [
          IconButton(
            tooltip: 'More',
            onPressed: () => _openMore(context),
            icon: const Icon(Icons.menu),
          ),
        ],
      ),
      body: child,
      bottomNavigationBar: NavigationBar(
        selectedIndex: index,
        onDestinationSelected: (i) {
          final target = _destinations[i].route;
          if (target != route) {
            Navigator.of(context).pushReplacementNamed(target);
          }
        },
        destinations: [
          for (final d in _destinations)
            NavigationDestination(
              icon: Icon(d.icon),
              selectedIcon: Icon(d.selectedIcon),
              label: d.label,
            ),
        ],
      ),
    );
  }

  void _openMore(BuildContext context) {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (ctx) {
        final items = <MapEntry<String, String>>[
          const MapEntry(AppRouter.evidence, 'Evidence'),
          const MapEntry(AppRouter.risks, 'Risks'),
          const MapEntry(AppRouter.memory, 'Decision Memory'),
          const MapEntry(AppRouter.outcome, 'Outcome Review'),
          const MapEntry(AppRouter.nexAi, 'NEX AI'),
          const MapEntry(AppRouter.membership, 'Membership'),
          const MapEntry(AppRouter.privacy, 'Privacy'),
          const MapEntry(AppRouter.notifications, 'Notification Settings'),
        ];
        return ListView(
          children: [
            for (final e in items)
              ListTile(
                title: Text(e.value),
                onTap: () {
                  Navigator.pop(ctx);
                  Navigator.of(context).pushReplacementNamed(e.key);
                },
              ),
          ],
        );
      },
    );
  }
}

class _NavDest {
  const _NavDest(this.route, this.icon, this.selectedIcon, this.label);
  final String route;
  final IconData icon;
  final IconData selectedIcon;
  final String label;
}
