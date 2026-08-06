/// Shared public entitlement DTO — mirrors server authority (V18.2).
library;

class PublicEntitlementDto {
  const PublicEntitlementDto({
    required this.plan,
    required this.policyVersion,
    required this.capabilities,
    required this.limits,
    required this.brandStatus,
    required this.pricingStatus,
    required this.billingStatus,
  });

  final String plan;
  final String policyVersion;
  final List<String> capabilities;
  final Map<String, dynamic> limits;
  final String brandStatus;
  final String pricingStatus;
  final String billingStatus;

  factory PublicEntitlementDto.fromJson(Map<String, dynamic> json) {
    final brand = json['brand'] as Map<String, dynamic>? ?? {};
    return PublicEntitlementDto(
      plan: json['plan'] as String? ?? 'VISITOR',
      policyVersion: json['policy_version'] as String? ?? '',
      capabilities: (json['capabilities'] as List<dynamic>? ?? [])
          .map((e) => e.toString())
          .toList(),
      limits: Map<String, dynamic>.from(json['limits'] as Map? ?? {}),
      brandStatus: brand['brand_status'] as String? ?? 'BRAND_TBD',
      pricingStatus: brand['pricing_status'] as String? ?? 'PRICING_TBD',
      billingStatus: brand['billing_status'] as String? ?? 'NOT_STARTED',
    );
  }
}

/// Member navigation contract (V18.2) — parity with web primary nav.
const memberPrimaryNavV182 = [
  ('/home', 'overview'),
  ('/scanner', 'scanner'),
  ('/alerts', 'alerts'),
  ('/intelligence', 'intelligence'),
];

const memberNavigationContractId = 'member_navigation_contract_v18_2';
