import 'package:flutter_test/flutter_test.dart';
import 'package:nexus_public_mobile/core/deeplink/deep_link_router.dart';
import 'package:nexus_public_mobile/core/mode/app_mode.dart';
import 'package:nexus_public_mobile/data/dto/availability.dart';
import 'package:nexus_public_mobile/data/mock/mock_public_data.dart';
import 'package:nexus_public_mobile/data/repositories/public_repository.dart';

void main() {
  test('mock market overview is DEMO_DATA', () {
    final dto = MockPublicData.marketOverview();
    expect(dto.demo, isTrue);
    expect(dto.symbols, isNotEmpty);
  });

  test('repository mock mode returns decisions', () async {
    final repo = PublicRepository.forMode(AppMode.mock);
    final decisions = await repo.decisions();
    expect(decisions.length, greaterThan(0));
    expect(decisions.first.demo, isTrue);
  });

  test('deep link routes decision detail', () {
    final link = DeepLinkRouter.parse(Uri.parse('nexus://public/decisions/dec_demo_001'));
    expect(link, isNotNull);
    expect(DeepLinkRouter.routeNameFor(link!), 'detail');
    expect(link.decisionId, 'dec_demo_001');
  });

  test('availability wire roundtrip', () {
    expect(availabilityFrom('STALE'), Availability.stale);
    expect(availabilityToWire(Availability.blocked), 'BLOCKED');
  });
}
