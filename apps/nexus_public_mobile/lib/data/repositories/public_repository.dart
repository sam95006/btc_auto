import '../../core/cache/offline_cache.dart';
import '../../core/mode/app_mode.dart';
import '../dto/decision_dto.dart';
import '../dto/market_dto.dart';
import '../live/live_public_client.dart';
import '../mock/mock_public_data.dart';

/// Repository boundary for public DTOs only.
class PublicRepository {
  PublicRepository({
    required this.mode,
    required OfflineCache cache,
    LivePublicClient? liveClient,
  })  : _cache = cache,
        _live = liveClient ?? LivePublicClient();

  final AppMode mode;
  final OfflineCache _cache;
  final LivePublicClient _live;

  factory PublicRepository.forMode(AppMode mode) {
    return PublicRepository(mode: mode, cache: MemoryOfflineCache());
  }

  Future<PublicMarketOverviewDto> marketOverview() async {
    if (mode.isMock) {
      final dto = MockPublicData.marketOverview();
      await _cache.put('market_overview', dto.toJson());
      return dto;
    }
    try {
      final dto = await _live.fetchMarketOverview();
      await _cache.put('market_overview', dto.toJson());
      return dto;
    } catch (_) {
      final cached = await _cache.get('market_overview');
      if (cached != null) return PublicMarketOverviewDto.fromJson(cached);
      rethrow;
    }
  }

  Future<List<PublicDecisionSummaryDto>> decisions() async {
    if (mode.isMock) return MockPublicData.decisions();
    return _live.fetchDecisions();
  }

  Future<PublicDecisionDetailDto?> decisionDetail(String id) async {
    if (mode.isMock) return MockPublicData.decisionDetail(id);
    return _live.fetchDecisionDetail(id);
  }

  Future<List<PublicEvidenceDto>> evidence({String? decisionId}) async {
    if (mode.isMock) return MockPublicData.evidence(decisionId: decisionId);
    return _live.fetchEvidence(decisionId: decisionId);
  }

  Future<List<PublicRiskConditionDto>> risks({String? decisionId}) async {
    if (mode.isMock) return MockPublicData.risks(decisionId: decisionId);
    return _live.fetchRisks(decisionId: decisionId);
  }

  Future<List<PublicAlertDto>> alerts() async {
    if (mode.isMock) return MockPublicData.alerts();
    return _live.fetchAlerts();
  }

  Future<List<PublicDecisionSummaryDto>> decisionMemory() async {
    if (mode.isMock) return MockPublicData.decisionMemory();
    return _live.fetchDecisionMemory();
  }

  Future<List<PublicOutcomeReviewDto>> outcomeReviews() async {
    if (mode.isMock) return MockPublicData.outcomeReviews();
    return _live.fetchOutcomeReviews();
  }

  Future<PublicMembershipDto> membership() async {
    if (mode.isMock) return MockPublicData.membership();
    return _live.fetchMembership();
  }

  Future<PublicAccountDto> account() async {
    if (mode.isMock) return MockPublicData.account();
    return _live.fetchAccount();
  }

  Future<String> nexAiReply(String prompt) async {
    if (mode.isMock) {
      return MockPublicData.nexAiReply(prompt);
    }
    return _live.fetchNexAiReply(prompt);
  }
}
