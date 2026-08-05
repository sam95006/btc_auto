import 'availability.dart';

/// Public Decision Object DTO — no strategy IDs, orders, positions, wallets, or secrets.
class PublicDecisionSummaryDto {
  const PublicDecisionSummaryDto({
    required this.id,
    required this.schemaVersion,
    required this.title,
    required this.posture,
    required this.confidence,
    required this.asOf,
    required this.availability,
    this.symbol,
    this.thesisHeadline,
    this.demo = false,
  });

  final String id;
  final String schemaVersion;
  final String title;
  final String posture;
  final double confidence;
  final DateTime asOf;
  final Availability availability;
  final String? symbol;
  final String? thesisHeadline;
  final bool demo;

  factory PublicDecisionSummaryDto.fromJson(Map<String, dynamic> json) {
    return PublicDecisionSummaryDto(
      id: json['id'] as String,
      schemaVersion: json['schema_version'] as String? ?? '1',
      title: json['title'] as String? ?? '',
      posture: json['posture'] as String? ?? 'stand_aside',
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0,
      asOf: DateTime.parse(json['as_of'] as String),
      availability: availabilityFrom(json['availability'] as String?),
      symbol: json['symbol'] as String?,
      thesisHeadline: json['thesis_headline'] as String?,
      demo: json['demo'] as bool? ?? false,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'schema_version': schemaVersion,
        'title': title,
        'posture': posture,
        'confidence': confidence,
        'as_of': asOf.toIso8601String(),
        'availability': availabilityToWire(availability),
        'symbol': symbol,
        'thesis_headline': thesisHeadline,
        'demo': demo,
      };
}

class PublicDecisionDetailDto {
  const PublicDecisionDetailDto({
    required this.summary,
    required this.contextNotes,
    required this.humanRationale,
    required this.aiAssistSummary,
    required this.evidenceIds,
    required this.riskIds,
    this.outcomeId,
  });

  final PublicDecisionSummaryDto summary;
  final String contextNotes;
  final String humanRationale;
  final String aiAssistSummary;
  final List<String> evidenceIds;
  final List<String> riskIds;
  final String? outcomeId;

  factory PublicDecisionDetailDto.fromJson(Map<String, dynamic> json) {
    return PublicDecisionDetailDto(
      summary: PublicDecisionSummaryDto.fromJson(
        json['summary'] as Map<String, dynamic>,
      ),
      contextNotes: json['context_notes'] as String? ?? '',
      humanRationale: json['human_rationale'] as String? ?? '',
      aiAssistSummary: json['ai_assist_summary'] as String? ?? '',
      evidenceIds: (json['evidence_ids'] as List<dynamic>? ?? [])
          .map((e) => e.toString())
          .toList(),
      riskIds: (json['risk_ids'] as List<dynamic>? ?? [])
          .map((e) => e.toString())
          .toList(),
      outcomeId: json['outcome_id'] as String?,
    );
  }
}

class PublicEvidenceDto {
  const PublicEvidenceDto({
    required this.id,
    required this.source,
    required this.summary,
    required this.polarity,
    required this.observedAt,
    required this.availability,
    this.freshnessLabel,
  });

  final String id;
  final String source;
  final String summary;
  final String polarity; // supporting | contradicting
  final DateTime observedAt;
  final Availability availability;
  final String? freshnessLabel;

  factory PublicEvidenceDto.fromJson(Map<String, dynamic> json) {
    return PublicEvidenceDto(
      id: json['id'] as String,
      source: json['source'] as String? ?? 'unknown',
      summary: json['summary'] as String? ?? '',
      polarity: json['polarity'] as String? ?? 'supporting',
      observedAt: DateTime.parse(json['observed_at'] as String),
      availability: availabilityFrom(json['availability'] as String?),
      freshnessLabel: json['freshness_label'] as String?,
    );
  }
}

class PublicRiskConditionDto {
  const PublicRiskConditionDto({
    required this.id,
    required this.label,
    required this.severity,
    required this.availability,
    this.invalidationNote,
  });

  final String id;
  final String label;
  final String severity;
  final Availability availability;
  final String? invalidationNote;

  factory PublicRiskConditionDto.fromJson(Map<String, dynamic> json) {
    return PublicRiskConditionDto(
      id: json['id'] as String,
      label: json['label'] as String? ?? '',
      severity: json['severity'] as String? ?? 'info',
      availability: availabilityFrom(json['availability'] as String?),
      invalidationNote: json['invalidation_note'] as String?,
    );
  }
}

class PublicAlertDto {
  const PublicAlertDto({
    required this.id,
    required this.title,
    required this.category,
    required this.createdAt,
    required this.availability,
    this.decisionId,
    this.body,
  });

  final String id;
  final String title;
  final String category;
  final DateTime createdAt;
  final Availability availability;
  final String? decisionId;
  final String? body;

  factory PublicAlertDto.fromJson(Map<String, dynamic> json) {
    return PublicAlertDto(
      id: json['id'] as String,
      title: json['title'] as String? ?? '',
      category: json['category'] as String? ?? 'generic',
      createdAt: DateTime.parse(json['created_at'] as String),
      availability: availabilityFrom(json['availability'] as String?),
      decisionId: json['decision_id'] as String?,
      body: json['body'] as String?,
    );
  }
}

class PublicOutcomeReviewDto {
  const PublicOutcomeReviewDto({
    required this.id,
    required this.decisionId,
    required this.processQuality,
    required this.outcomeLabel,
    required this.reviewedAt,
    required this.availability,
    this.notes,
  });

  final String id;
  final String decisionId;
  final String processQuality;
  final String outcomeLabel;
  final DateTime reviewedAt;
  final Availability availability;
  final String? notes;

  factory PublicOutcomeReviewDto.fromJson(Map<String, dynamic> json) {
    return PublicOutcomeReviewDto(
      id: json['id'] as String,
      decisionId: json['decision_id'] as String,
      processQuality: json['process_quality'] as String? ?? 'UNDETERMINED',
      outcomeLabel: json['outcome_label'] as String? ?? 'UNDETERMINED',
      reviewedAt: DateTime.parse(json['reviewed_at'] as String),
      availability: availabilityFrom(json['availability'] as String?),
      notes: json['notes'] as String?,
    );
  }
}

class PublicMembershipDto {
  const PublicMembershipDto({
    required this.tier,
    required this.status,
    this.renewalLabel,
  });

  final String tier; // Free | Pro | Elite | Enterprise
  final String status;
  final String? renewalLabel;

  factory PublicMembershipDto.fromJson(Map<String, dynamic> json) {
    return PublicMembershipDto(
      tier: json['tier'] as String? ?? 'Free',
      status: json['status'] as String? ?? 'active',
      renewalLabel: json['renewal_label'] as String?,
    );
  }
}

class PublicAccountDto {
  const PublicAccountDto({
    required this.displayName,
    required this.emailMasked,
    required this.locale,
  });

  final String displayName;
  final String emailMasked;
  final String locale;

  factory PublicAccountDto.fromJson(Map<String, dynamic> json) {
    return PublicAccountDto(
      displayName: json['display_name'] as String? ?? 'Member',
      emailMasked: json['email_masked'] as String? ?? '***',
      locale: json['locale'] as String? ?? 'en',
    );
  }
}
