import 'package:flutter_test/flutter_test.dart';
import 'package:nexus_public_mobile/core/flags/feature_flags.dart';
import 'package:nexus_public_mobile/core/subscription/subscription_boundary.dart';
import 'package:nexus_public_mobile/ui/navigation/member_nav_hooks.dart';

void main() {
  test('member buyable catalog excludes forbidden products', () {
    final snap = subscriptionBoundarySnapshot();
    final buyable = (snap['buyable'] as Map).keys.cast<String>().toSet();
    final forbidden = (snap['not_for_sale'] as Map).keys.cast<String>().toSet();
    expect(buyable.isDisjoint(forbidden), isTrue);
    expect(snap['member_execution_control_count'], 0);
    expect(snap['execution_controls'], isFalse);
    expect(snap['live_billing_enabled'], isFalse);
  });

  test('nav hooks never expose execution routes', () {
    final all = allMemberNavRoutes();
    for (final bad in [
      '/auto-trading',
      '/copy-trading',
      '/exchange-execution',
      '/private-strategy',
      '/founder-portfolio',
    ]) {
      expect(all.contains(bad), isFalse);
    }
    expect(countMemberExecutionControls(all), 0);
    expect(memberNavHookSnapshot()['member_execution_control_count'], 0);
  });

  test('forbidden feature flags cannot be enabled', () {
    final flags = FeatureFlagStore.defaults();
    expect(flags.isEnabled('auto_trading'), isFalse);
    expect(flags.isEnabled('copy_trading'), isFalse);
    expect(flags.isEnabled('exchange_execution'), isFalse);
    expect(flags.isEnabled('private_strategy'), isFalse);
    expect(flags.isEnabled('founder_portfolio_access'), isFalse);
    expect(flags.isEnabled('execution_controls'), isFalse);
    expect(
      () => flags.set('auto_trading', true),
      throwsA(isA<StateError>()),
    );
  });

  test('forbidden products are not buyable', () {
    expect(isBuyableMemberProduct('market_data'), isTrue);
    expect(isBuyableMemberProduct('auto_trading'), isFalse);
    expect(isForbiddenMemberProduct('founder_portfolio_access'), isTrue);
  });
}
