import '../dto/availability.dart';
import '../dto/decision_dto.dart';
import '../dto/market_dto.dart';

/// Fixture public DTOs for mock mode. Always mark demo=true where applicable.
class MockPublicData {
  static final _now = DateTime.utc(2026, 8, 5, 12);

  static PublicMarketOverviewDto marketOverview() {
    return PublicMarketOverviewDto(
      schemaVersion: '1',
      asOf: _now,
      retrievedAt: _now,
      availability: Availability.available,
      freshnessLabel: 'mock',
      demo: true,
      symbols: const [
        PublicMarketSymbolDto(
          symbol: 'BTC-USD',
          lastPrice: 64000,
          change24hPct: 1.2,
        ),
        PublicMarketSymbolDto(
          symbol: 'ETH-USD',
          lastPrice: 3200,
          change24hPct: -0.4,
        ),
      ],
    );
  }

  static List<PublicDecisionSummaryDto> decisions() {
    return [
      PublicDecisionSummaryDto(
        id: 'dec_demo_001',
        schemaVersion: '1',
        title: 'BTC stand-aside near resistance',
        posture: 'stand_aside',
        confidence: 0.62,
        asOf: _now,
        availability: Availability.available,
        symbol: 'BTC-USD',
        thesisHeadline: 'Wait for invalidation clarity',
        demo: true,
      ),
      PublicDecisionSummaryDto(
        id: 'dec_demo_002',
        schemaVersion: '1',
        title: 'ETH reduce exposure thesis',
        posture: 'reduce',
        confidence: 0.55,
        asOf: _now.subtract(const Duration(hours: 6)),
        availability: Availability.stale,
        symbol: 'ETH-USD',
        thesisHeadline: 'Funding elevated vs spot',
        demo: true,
      ),
    ];
  }

  static PublicDecisionDetailDto? decisionDetail(String id) {
    final summary = decisions().where((d) => d.id == id).firstOrNull;
    if (summary == null) return null;
    return PublicDecisionDetailDto(
      summary: summary,
      contextNotes: 'Mock context snapshot — DEMO_DATA',
      humanRationale: 'Prefer waiting for clearer invalidation.',
      aiAssistSummary: 'AI assist (sanitized): confidence moderate; no order advice.',
      evidenceIds: const ['ev_1', 'ev_2'],
      riskIds: const ['risk_1'],
      outcomeId: id == 'dec_demo_002' ? 'out_1' : null,
    );
  }

  static List<PublicEvidenceDto> evidence({String? decisionId}) {
    return [
      PublicEvidenceDto(
        id: 'ev_1',
        source: 'public_market_summary',
        summary: 'Spot momentum cooling on 4h window.',
        polarity: 'supporting',
        observedAt: _now.subtract(const Duration(hours: 2)),
        availability: Availability.available,
        freshnessLabel: '2h',
      ),
      PublicEvidenceDto(
        id: 'ev_2',
        source: 'public_derivatives_summary',
        summary: 'Funding elevated — counter-evidence to aggressive posture.',
        polarity: 'contradicting',
        observedAt: _now.subtract(const Duration(hours: 1)),
        availability: Availability.available,
        freshnessLabel: '1h',
      ),
    ];
  }

  static List<PublicRiskConditionDto> risks({String? decisionId}) {
    return const [
      PublicRiskConditionDto(
        id: 'risk_1',
        label: 'Thesis invalid if daily close above prior high',
        severity: 'medium',
        availability: Availability.available,
        invalidationNote: 'User-owned advisory rule',
      ),
    ];
  }

  static List<PublicAlertDto> alerts() {
    return [
      PublicAlertDto(
        id: 'alert_1',
        title: 'Decision freshness degraded',
        category: 'stale',
        createdAt: _now,
        availability: Availability.available,
        decisionId: 'dec_demo_002',
        body: 'ETH decision marked STALE in mock feed.',
      ),
    ];
  }

  static List<PublicDecisionSummaryDto> decisionMemory() => decisions();

  static List<PublicOutcomeReviewDto> outcomeReviews() {
    return [
      PublicOutcomeReviewDto(
        id: 'out_1',
        decisionId: 'dec_demo_002',
        processQuality: 'GOOD_PROCESS',
        outcomeLabel: 'UNDETERMINED',
        reviewedAt: _now,
        availability: Availability.available,
        notes: 'Process review only — DEMO_DATA',
      ),
    ];
  }

  static PublicMembershipDto membership() {
    return const PublicMembershipDto(
      tier: 'Free',
      status: 'active',
      renewalLabel: 'No live billing in foundation',
    );
  }

  static PublicAccountDto account() {
    return const PublicAccountDto(
      displayName: 'Demo Member',
      emailMasked: 'd***@example.com',
      locale: 'en',
    );
  }

  static String nexAiReply(String prompt) {
    return 'NEX AI (mock): I can discuss Decision context and evidence only. '
        'No exchange orders. Prompt echo length=${prompt.length}. DEMO_DATA';
  }
}

extension _FirstOrNull<E> on Iterable<E> {
  E? get firstOrNull {
    final it = iterator;
    if (it.moveNext()) return it.current;
    return null;
  }
}
