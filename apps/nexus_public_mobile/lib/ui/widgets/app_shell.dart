import 'package:flutter/material.dart';

import '../navigation/app_router.dart';
import '../navigation/member_nav_hooks.dart';

class AppShell extends StatelessWidget {
  const AppShell({super.key, required this.child});

  final Widget child;

  static const _destinationMeta = <String, _NavDest>{
    AppRouter.home: _NavDest(AppRouter.home, Icons.home_outlined, Icons.home, 'Home'),
    AppRouter.markets: _NavDest(
        AppRouter.markets, Icons.show_chart_outlined, Icons.show_chart, 'Markets'),
    AppRouter.decisions: _NavDest(AppRouter.decisions, Icons.account_tree_outlined,
        Icons.account_tree, 'Decisions'),
    AppRouter.alerts: _NavDest(AppRouter.alerts, Icons.notifications_outlined,
        Icons.notifications, 'Alerts'),
    AppRouter.account:
        _NavDest(AppRouter.account, Icons.person_outline, Icons.person, 'Account'),
  };

  static const _secondaryLabels = <String, String>{
    AppRouter.evidence: 'Evidence',
    AppRouter.risks: 'Risks',
    AppRouter.memory: 'Decision Memory',
    AppRouter.outcome: 'Outcome Review',
    AppRouter.nexAi: 'NEX AI',
    AppRouter.membership: 'Membership',
    AppRouter.privacy: 'Privacy',
    AppRouter.notifications: 'Notification Settings',
  };

  @override
  Widget build(BuildContext context) {
    final route = ModalRoute.of(context)?.settings.name ?? AppRouter.home;
    final destinations = [
      for (final r in memberPrimaryNavRoutes())
        if (_destinationMeta.containsKey(r)) _destinationMeta[r]!,
    ];
    final selected = destinations.indexWhere((d) => d.route == route);
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
        selectedIndex: index.clamp(0, destinations.length - 1),
        onDestinationSelected: (i) {
          final target = destinations[i].route;
          if (target != route) {
            Navigator.of(context).pushReplacementNamed(target);
          }
        },
        destinations: [
          for (final d in destinations)
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
          for (final r in memberSecondaryNavRoutes())
            MapEntry(r, _secondaryLabels[r] ?? r),
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
