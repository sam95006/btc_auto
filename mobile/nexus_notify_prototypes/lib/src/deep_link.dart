/// Deep-link builder/parser prototype for nexus://app routes.
class DeepLinkRouter {
  DeepLinkRouter({this.scheme = 'nexus', this.host = 'app'});

  final String scheme;
  final String host;

  static const routes = <String>{
    'home',
    'markets',
    'decisions',
    'decision_detail',
    'evidence',
    'risks',
    'alerts',
    'decision_memory',
    'outcome_review',
    'nex_ai',
    'membership',
    'account',
    'privacy',
    'notification_settings',
    'thesis_monitor',
  };

  static const privateDenied = <String>{
    'founder',
    'private',
    'execution',
    'exchange',
    'wallet',
    'checkpoint',
    'lesson_memory',
    'reflection',
    'qualification_admin',
    'kill_switch',
  };

  String build(String route, [Map<String, String> params = const {}]) {
    if (!routes.contains(route)) {
      throw ArgumentError('unknown deep-link route: $route');
    }
    if (privateDenied.contains(route)) {
      throw StateError('HARD BAN: private deep-link route refused: $route');
    }
    final q = params.entries.map((e) => '${e.key}=${Uri.encodeQueryComponent(e.value)}').join('&');
    final base = '$scheme://$host/$route';
    return q.isEmpty ? base : '$base?$q';
  }

  Uri parse(String uri) {
    final parsed = Uri.parse(uri);
    if (parsed.scheme != scheme || parsed.host != host) {
      throw ArgumentError('unsupported deep-link URI: $uri');
    }
    final route = parsed.pathSegments.isEmpty ? '' : parsed.pathSegments.first;
    if (privateDenied.contains(route)) {
      throw StateError('HARD BAN: private deep-link route refused: $route');
    }
    if (!routes.contains(route)) {
      throw ArgumentError('unknown deep-link route: $route');
    }
    return parsed;
  }
}
