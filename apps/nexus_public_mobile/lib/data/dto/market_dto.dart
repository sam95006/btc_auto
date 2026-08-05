import 'availability.dart';

/// Public market overview DTO — sanitized fields only.
class PublicMarketOverviewDto {
  const PublicMarketOverviewDto({
    required this.schemaVersion,
    required this.asOf,
    required this.retrievedAt,
    required this.symbols,
    required this.availability,
    this.freshnessLabel,
    this.demo = false,
  });

  final String schemaVersion;
  final DateTime asOf;
  final DateTime retrievedAt;
  final List<PublicMarketSymbolDto> symbols;
  final Availability availability;
  final String? freshnessLabel;
  final bool demo;

  factory PublicMarketOverviewDto.fromJson(Map<String, dynamic> json) {
    final list = (json['symbols'] as List<dynamic>? ?? [])
        .map((e) => PublicMarketSymbolDto.fromJson(e as Map<String, dynamic>))
        .toList();
    return PublicMarketOverviewDto(
      schemaVersion: json['schema_version'] as String? ?? '1',
      asOf: DateTime.parse(json['as_of'] as String),
      retrievedAt: DateTime.parse(json['retrieved_at'] as String),
      symbols: list,
      availability: availabilityFrom(json['availability'] as String?),
      freshnessLabel: json['freshness_label'] as String?,
      demo: json['demo'] as bool? ?? false,
    );
  }

  Map<String, dynamic> toJson() => {
        'schema_version': schemaVersion,
        'as_of': asOf.toIso8601String(),
        'retrieved_at': retrievedAt.toIso8601String(),
        'symbols': symbols.map((s) => s.toJson()).toList(),
        'availability': availabilityToWire(availability),
        'freshness_label': freshnessLabel,
        'demo': demo,
      };
}

class PublicMarketSymbolDto {
  const PublicMarketSymbolDto({
    required this.symbol,
    this.lastPrice,
    this.change24hPct,
    this.availability = Availability.available,
  });

  final String symbol;
  final double? lastPrice;
  final double? change24hPct;
  final Availability availability;

  factory PublicMarketSymbolDto.fromJson(Map<String, dynamic> json) {
    return PublicMarketSymbolDto(
      symbol: json['symbol'] as String,
      lastPrice: (json['last_price'] as num?)?.toDouble(),
      change24hPct: (json['change_24h_pct'] as num?)?.toDouble(),
      availability: availabilityFrom(json['availability'] as String?),
    );
  }

  Map<String, dynamic> toJson() => {
        'symbol': symbol,
        'last_price': lastPrice,
        'change_24h_pct': change24hPct,
        'availability': availabilityToWire(availability),
      };
}
