/// Deep-link routing for public Decision Intelligence surfaces.
class DeepLinkRouter {
  static const scheme = 'nexus';
  static const host = 'public';

  /// Parses `nexus://public/<path>` or `https://app.nexus.example/<path>`.
  static DeepLink? parse(Uri uri) {
    final pathSegments = uri.pathSegments.where((s) => s.isNotEmpty).toList();
    if (uri.scheme == scheme && uri.host == host) {
      return DeepLink(path: pathSegments, query: uri.queryParameters);
    }
    if (uri.scheme == 'https' && pathSegments.isNotEmpty) {
      return DeepLink(path: pathSegments, query: uri.queryParameters);
    }
    return null;
  }

  static String? routeNameFor(DeepLink link) {
    if (link.path.isEmpty) return 'home';
    switch (link.path.first) {
      case 'markets':
        return 'markets';
      case 'decisions':
        return link.path.length > 1 ? 'detail' : 'decisions';
      case 'evidence':
        return 'evidence';
      case 'risks':
        return 'risks';
      case 'alerts':
        return 'alerts';
      case 'memory':
        return 'memory';
      case 'outcome':
        return 'outcome';
      case 'nex-ai':
        return 'nex_ai';
      case 'membership':
        return 'membership';
      case 'account':
        return 'account';
      case 'privacy':
        return 'privacy';
      case 'notifications':
        return 'notifications';
      default:
        return 'home';
    }
  }
}

class DeepLink {
  const DeepLink({required this.path, required this.query});
  final List<String> path;
  final Map<String, String> query;

  String? get decisionId {
    if (path.length >= 2 && path.first == 'decisions') return path[1];
    return query['decisionId'];
  }
}
