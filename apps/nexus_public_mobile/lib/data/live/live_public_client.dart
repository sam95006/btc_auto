import 'dart:convert';

import 'package:flutter/foundation.dart';

import '../dto/decision_dto.dart';
import '../dto/market_dto.dart';

/// Live HTTP client stub for public Decision Cloud endpoints.
/// Foundation wires URL + JSON parsing against public API hosts only.
class LivePublicClient {
  LivePublicClient({
    this.baseUrl = const String.fromEnvironment(
      'NEXUS_PUBLIC_API_BASE',
      defaultValue: 'http://127.0.0.1:8080',
    ),
    HttpGet? httpGet,
  }) : _httpGet = httpGet;

  final String baseUrl;
  final HttpGet? _httpGet;

  Future<Map<String, dynamic>> _getJson(String path) async {
    final getter = _httpGet;
    if (getter == null) {
      throw StateError(
        'LivePublicClient requires an HttpGet inject or platform http binding. '
        'Use mock mode when offline.',
      );
    }
    final body = await getter('$baseUrl$path');
    return jsonDecode(body) as Map<String, dynamic>;
  }

  Future<PublicMarketOverviewDto> fetchMarketOverview() async {
    final json = await _getJson('/v1/public/markets/overview');
    return PublicMarketOverviewDto.fromJson(json);
  }

  Future<List<PublicDecisionSummaryDto>> fetchDecisions() async {
    final json = await _getJson('/v1/public/decisions');
    final items = json['items'] as List<dynamic>? ?? [];
    return items
        .map((e) => PublicDecisionSummaryDto.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<PublicDecisionDetailDto?> fetchDecisionDetail(String id) async {
    final json = await _getJson('/v1/public/decisions/$id');
    return PublicDecisionDetailDto.fromJson(json);
  }

  Future<List<PublicEvidenceDto>> fetchEvidence({String? decisionId}) async {
    final q = decisionId == null ? '' : '?decision_id=$decisionId';
    final json = await _getJson('/v1/public/evidence$q');
    final items = json['items'] as List<dynamic>? ?? [];
    return items
        .map((e) => PublicEvidenceDto.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<PublicRiskConditionDto>> fetchRisks({String? decisionId}) async {
    final q = decisionId == null ? '' : '?decision_id=$decisionId';
    final json = await _getJson('/v1/public/risks$q');
    final items = json['items'] as List<dynamic>? ?? [];
    return items
        .map((e) => PublicRiskConditionDto.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<PublicAlertDto>> fetchAlerts() async {
    final json = await _getJson('/v1/public/alerts');
    final items = json['items'] as List<dynamic>? ?? [];
    return items
        .map((e) => PublicAlertDto.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<PublicDecisionSummaryDto>> fetchDecisionMemory() async {
    final json = await _getJson('/v1/public/decision-memory');
    final items = json['items'] as List<dynamic>? ?? [];
    return items
        .map((e) => PublicDecisionSummaryDto.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<PublicOutcomeReviewDto>> fetchOutcomeReviews() async {
    final json = await _getJson('/v1/public/outcome-reviews');
    final items = json['items'] as List<dynamic>? ?? [];
    return items
        .map((e) => PublicOutcomeReviewDto.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<PublicMembershipDto> fetchMembership() async {
    final json = await _getJson('/v1/public/membership');
    return PublicMembershipDto.fromJson(json);
  }

  Future<PublicAccountDto> fetchAccount() async {
    final json = await _getJson('/v1/public/account');
    return PublicAccountDto.fromJson(json);
  }

  Future<String> fetchNexAiReply(String prompt) async {
    final json = await _getJson('/v1/public/nex-ai');
    return json['reply'] as String? ?? 'UNAVAILABLE';
  }
}

typedef HttpGet = Future<String> Function(String url);

@visibleForTesting
void debugLiveClientNoop() {}
