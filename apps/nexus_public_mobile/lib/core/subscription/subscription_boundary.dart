/// PUB17-D subscription product boundary — mobile catalog & nav hooks.
library subscription_boundary;

/// Products members may buy (intelligence / context only).
const memberBuyableProducts = <String, String>{
  'market_data': 'Market Data',
  'ai_intelligence': 'AI Intelligence',
  'decision_context': 'Decision Context',
  'risk_explanation': 'Risk Explanation',
  'alerts': 'Alerts',
  'historical_comparisons': 'Historical Comparisons',
  'global_market_briefs': 'Global Market Briefs',
};

/// Products members must never buy.
const memberForbiddenProducts = <String, String>{
  'auto_trading': 'Auto Trading',
  'copy_trading': 'Copy Trading',
  'exchange_execution': 'Exchange Execution',
  'private_strategy': 'Private Strategy',
  'founder_portfolio_access': 'Founder Portfolio Access',
};

const forbiddenMemberRoutes = <String>{
  '/auto-trading',
  '/copy-trading',
  '/exchange-execution',
  '/private-strategy',
  '/founder-portfolio',
  '/execution',
  '/trade',
};

bool isForbiddenMemberProduct(String productId) {
  final id = productId.trim().toLowerCase().replaceAll('-', '_');
  return memberForbiddenProducts.containsKey(id) ||
      id == 'execution_controls' ||
      id == 'execution_control';
}

bool isBuyableMemberProduct(String productId) {
  final id = productId.trim().toLowerCase().replaceAll('-', '_');
  if (isForbiddenMemberProduct(id)) return false;
  return memberBuyableProducts.containsKey(id);
}

/// Filter nav routes — drops any execution / forbidden destinations.
List<String> filterMemberNavRoutes(Iterable<String> routes) {
  return [
    for (final r in routes)
      if (!forbiddenMemberRoutes.contains(r)) r,
  ];
}

void assertMemberNavRoutesClean(Iterable<String> routes) {
  for (final r in routes) {
    if (forbiddenMemberRoutes.contains(r)) {
      throw StateError('HARD BAN: member mobile nav includes forbidden route $r');
    }
  }
}

/// member_execution_control_count — must remain 0.
int countMemberExecutionControls(Iterable<String> surfaces) {
  var count = 0;
  for (final s in surfaces) {
    if (isForbiddenMemberProduct(s)) count += 1;
  }
  return count;
}

Map<String, Object?> subscriptionBoundarySnapshot() {
  return {
    'buyable': memberBuyableProducts,
    'not_for_sale': memberForbiddenProducts,
    'live_billing_enabled': false,
    'member_execution_control_count': 0,
    'execution_controls': false,
  };
}
