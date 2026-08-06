/// PUB17-D member mobile navigation hooks — intelligence products only.
import '../../core/subscription/subscription_boundary.dart';
import 'app_router.dart';

/// Primary shell destinations (never include execution / trading routes).
List<String> memberPrimaryNavRoutes() {
  final routes = filterMemberNavRoutes(const [
    AppRouter.home,
    AppRouter.markets,
    AppRouter.decisions,
    AppRouter.alerts,
    AppRouter.account,
  ]);
  assertMemberNavRoutesClean(routes);
  return routes;
}

/// Overflow / more-menu destinations.
List<String> memberSecondaryNavRoutes() {
  final routes = filterMemberNavRoutes(const [
    AppRouter.evidence,
    AppRouter.risks,
    AppRouter.memory,
    AppRouter.outcome,
    AppRouter.nexAi,
    AppRouter.membership,
    AppRouter.privacy,
    AppRouter.notifications,
  ]);
  assertMemberNavRoutesClean(routes);
  return routes;
}

/// All member-reachable routes — used by security tests.
List<String> allMemberNavRoutes() {
  final routes = filterMemberNavRoutes([
    ...memberPrimaryNavRoutes(),
    ...memberSecondaryNavRoutes(),
  ]);
  assertMemberNavRoutesClean(routes);
  if (countMemberExecutionControls(routes) != 0) {
    throw StateError('HARD BAN: member_execution_control_count must be 0');
  }
  return routes;
}

Map<String, Object?> memberNavHookSnapshot() {
  return {
    'primary': memberPrimaryNavRoutes(),
    'secondary': memberSecondaryNavRoutes(),
    'all': allMemberNavRoutes(),
    'member_execution_control_count': 0,
    'execution_controls': false,
    'forbidden_filtered': true,
  };
}
