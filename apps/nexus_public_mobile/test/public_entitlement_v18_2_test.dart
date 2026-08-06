import 'package:flutter_test/flutter_test.dart';
import 'package:nexus_public_mobile/data/dto/public_entitlement_dto.dart';

void main() {
  test('public entitlement dto parses server snapshot', () {
    final dto = PublicEntitlementDto.fromJson({
      'plan': 'FREE',
      'policy_version': 'v18_2_alpha_draft',
      'capabilities': ['WATCHLIST', 'AI_BASIC'],
      'limits': {'watchlist_max': 5},
      'brand': {
        'brand_status': 'BRAND_TBD',
        'pricing_status': 'PRICING_TBD',
        'billing_status': 'NOT_STARTED',
      },
    });
    expect(dto.plan, 'FREE');
    expect(dto.brandStatus, 'BRAND_TBD');
    expect(dto.limits['watchlist_max'], 5);
  });

  test('navigation contract has four primary routes', () {
    expect(memberPrimaryNavV182.length, 4);
    expect(memberNavigationContractId, 'member_navigation_contract_v18_2');
  });
}
