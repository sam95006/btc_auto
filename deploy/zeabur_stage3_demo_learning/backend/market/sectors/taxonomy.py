"""NEXUS curated crypto sector taxonomy (Phase 3).

Multi-membership · provenance · confidence. No runtime LLM guessing.
Read-only research intelligence — not trading signals.
"""
from __future__ import annotations

from typing import Any

# Sector catalog — NEXUS curated
SECTORS: list[dict[str, Any]] = [
    {"id": "layer1", "slug": "layer1", "nameZhTW": "Layer 1", "nameEn": "Layer 1", "iconKey": "l1", "descriptionZhTW": "獨立公鏈與基礎結算層。", "displayOrder": 10},
    {"id": "layer2", "slug": "layer2", "nameZhTW": "Layer 2", "nameEn": "Layer 2", "iconKey": "l2", "descriptionZhTW": "擴容與二層網路。", "displayOrder": 20},
    {"id": "btc-ecosystem", "slug": "btc-ecosystem", "nameZhTW": "BTC 生態", "nameEn": "BTC Ecosystem", "iconKey": "btc", "descriptionZhTW": "比特幣相關資產與生態。", "displayOrder": 30},
    {"id": "eth-ecosystem", "slug": "eth-ecosystem", "nameZhTW": "ETH 生態", "nameEn": "ETH Ecosystem", "iconKey": "eth", "descriptionZhTW": "以太坊生態與相關資產。", "displayOrder": 40},
    {"id": "sol-ecosystem", "slug": "sol-ecosystem", "nameZhTW": "SOL 生態", "nameEn": "SOL Ecosystem", "iconKey": "sol", "descriptionZhTW": "Solana 生態資產。", "displayOrder": 50},
    {"id": "defi", "slug": "defi", "nameZhTW": "DeFi", "nameEn": "DeFi", "iconKey": "defi", "descriptionZhTW": "去中心化金融協議。", "displayOrder": 60},
    {"id": "dex", "slug": "dex", "nameZhTW": "DEX", "nameEn": "DEX", "iconKey": "dex", "descriptionZhTW": "去中心化交易所。", "displayOrder": 70, "parentSectorId": "defi"},
    {"id": "lending", "slug": "lending", "nameZhTW": "Lending", "nameEn": "Lending", "iconKey": "lend", "descriptionZhTW": "借貸與貨幣市場。", "displayOrder": 80, "parentSectorId": "defi"},
    {"id": "liquid-staking", "slug": "liquid-staking", "nameZhTW": "Liquid Staking", "nameEn": "Liquid Staking", "iconKey": "lst", "descriptionZhTW": "流動性質押與衍生品。", "displayOrder": 90, "parentSectorId": "defi"},
    {"id": "ai", "slug": "ai", "nameZhTW": "AI", "nameEn": "AI", "iconKey": "ai", "descriptionZhTW": "AI 與運算相關加密資產。", "displayOrder": 100},
    {"id": "meme", "slug": "meme", "nameZhTW": "Meme", "nameEn": "Meme", "iconKey": "meme", "descriptionZhTW": "社群驅動的 Meme 資產。", "displayOrder": 110},
    {"id": "rwa", "slug": "rwa", "nameZhTW": "RWA", "nameEn": "RWA", "iconKey": "rwa", "descriptionZhTW": "現實世界資產代幣化。", "displayOrder": 120},
    {"id": "gamefi", "slug": "gamefi", "nameZhTW": "GameFi", "nameEn": "GameFi", "iconKey": "game", "descriptionZhTW": "鏈遊與 GameFi。", "displayOrder": 130},
    {"id": "infrastructure", "slug": "infrastructure", "nameZhTW": "Infrastructure", "nameEn": "Infrastructure", "iconKey": "infra", "descriptionZhTW": "基礎設施與開發者工具。", "displayOrder": 140},
    {"id": "depin", "slug": "depin", "nameZhTW": "DePIN", "nameEn": "DePIN", "iconKey": "depin", "descriptionZhTW": "去中心化實體基礎設施網路。", "displayOrder": 150},
    {"id": "oracle", "slug": "oracle", "nameZhTW": "Oracle", "nameEn": "Oracle", "iconKey": "oracle", "descriptionZhTW": "預言機與資料服務。", "displayOrder": 160},
    {"id": "privacy", "slug": "privacy", "nameZhTW": "Privacy", "nameEn": "Privacy", "iconKey": "priv", "descriptionZhTW": "隱私與加密通訊相關。", "displayOrder": 170},
    {"id": "interoperability", "slug": "interoperability", "nameZhTW": "Interoperability", "nameEn": "Interoperability", "iconKey": "bridge", "descriptionZhTW": "跨鏈與互操作性。", "displayOrder": 180},
    {"id": "storage", "slug": "storage", "nameZhTW": "Storage", "nameEn": "Storage", "iconKey": "store", "descriptionZhTW": "去中心化儲存。", "displayOrder": 190},
    {"id": "other", "slug": "other", "nameZhTW": "Other／Unclassified", "nameEn": "Other / Unclassified", "iconKey": "other", "descriptionZhTW": "尚未正式分類或涵蓋範圍外的標的。", "displayOrder": 999},
]

for s in SECTORS:
    s.setdefault("active", True)
    s.setdefault("source", "NEXUS_CURATED")
    s.setdefault("lastReviewedAt", 1_784_280_000_000)

# canonical base → sectors (multi). Exchange symbols may include 1000* prefixes.
_MEMBERSHIPS: dict[str, dict[str, Any]] = {
    "BTC": {"sectors": ["layer1", "btc-ecosystem"], "confidence": "HIGH"},
    "ETH": {"sectors": ["layer1", "eth-ecosystem"], "confidence": "HIGH"},
    "SOL": {"sectors": ["layer1", "sol-ecosystem"], "confidence": "HIGH"},
    "BNB": {"sectors": ["layer1"], "confidence": "HIGH"},
    "XRP": {"sectors": ["layer1"], "confidence": "HIGH"},
    "ADA": {"sectors": ["layer1"], "confidence": "HIGH"},
    "AVAX": {"sectors": ["layer1"], "confidence": "HIGH"},
    "DOT": {"sectors": ["layer1", "interoperability"], "confidence": "HIGH"},
    "ATOM": {"sectors": ["layer1", "interoperability"], "confidence": "HIGH"},
    "NEAR": {"sectors": ["layer1", "ai"], "confidence": "MEDIUM"},
    "SUI": {"sectors": ["layer1"], "confidence": "HIGH"},
    "APT": {"sectors": ["layer1"], "confidence": "HIGH"},
    "TON": {"sectors": ["layer1"], "confidence": "HIGH"},
    "TRX": {"sectors": ["layer1"], "confidence": "HIGH"},
    "SEI": {"sectors": ["layer1"], "confidence": "MEDIUM"},
    "INJ": {"sectors": ["layer1", "defi"], "confidence": "MEDIUM"},
    "TIA": {"sectors": ["layer1", "infrastructure"], "confidence": "MEDIUM"},
    "ARB": {"sectors": ["layer2", "eth-ecosystem"], "confidence": "HIGH"},
    "OP": {"sectors": ["layer2", "eth-ecosystem"], "confidence": "HIGH"},
    "MATIC": {"sectors": ["layer2", "eth-ecosystem"], "confidence": "HIGH"},
    "POL": {"sectors": ["layer2", "eth-ecosystem"], "confidence": "HIGH"},
    "STRK": {"sectors": ["layer2", "eth-ecosystem"], "confidence": "HIGH"},
    "ZK": {"sectors": ["layer2", "eth-ecosystem", "privacy"], "confidence": "MEDIUM"},
    "MANTA": {"sectors": ["layer2", "eth-ecosystem"], "confidence": "MEDIUM"},
    "BLAST": {"sectors": ["layer2", "eth-ecosystem"], "confidence": "MEDIUM"},
    "BASE": {"sectors": ["layer2", "eth-ecosystem"], "confidence": "LOW"},
    "UNI": {"sectors": ["defi", "dex", "eth-ecosystem"], "confidence": "HIGH"},
    "AAVE": {"sectors": ["defi", "lending", "eth-ecosystem"], "confidence": "HIGH"},
    "MKR": {"sectors": ["defi", "eth-ecosystem"], "confidence": "HIGH"},
    "CRV": {"sectors": ["defi", "dex", "eth-ecosystem"], "confidence": "HIGH"},
    "COMP": {"sectors": ["defi", "lending"], "confidence": "HIGH"},
    "SNX": {"sectors": ["defi", "eth-ecosystem"], "confidence": "HIGH"},
    "LDO": {"sectors": ["defi", "liquid-staking", "eth-ecosystem"], "confidence": "HIGH"},
    "PENDLE": {"sectors": ["defi", "eth-ecosystem"], "confidence": "MEDIUM"},
    "JUP": {"sectors": ["defi", "dex", "sol-ecosystem"], "confidence": "HIGH"},
    "RAY": {"sectors": ["defi", "dex", "sol-ecosystem"], "confidence": "HIGH"},
    "ORCA": {"sectors": ["defi", "dex", "sol-ecosystem"], "confidence": "MEDIUM"},
    "GMX": {"sectors": ["defi", "dex"], "confidence": "HIGH"},
    "DYDX": {"sectors": ["defi", "dex"], "confidence": "HIGH"},
    "CAKE": {"sectors": ["defi", "dex"], "confidence": "HIGH"},
    "SUSHI": {"sectors": ["defi", "dex"], "confidence": "MEDIUM"},
    "RENDER": {"sectors": ["ai", "depin", "sol-ecosystem"], "confidence": "HIGH"},
    "RNDR": {"sectors": ["ai", "depin"], "confidence": "HIGH"},
    "FET": {"sectors": ["ai"], "confidence": "HIGH"},
    "TAO": {"sectors": ["ai"], "confidence": "HIGH"},
    "WLD": {"sectors": ["ai"], "confidence": "MEDIUM"},
    "AI": {"sectors": ["ai"], "confidence": "MEDIUM"},
    "AKT": {"sectors": ["ai", "depin", "infrastructure"], "confidence": "MEDIUM"},
    "NOS": {"sectors": ["ai", "sol-ecosystem"], "confidence": "MEDIUM"},
    "DOGE": {"sectors": ["meme"], "confidence": "HIGH"},
    "SHIB": {"sectors": ["meme", "eth-ecosystem"], "confidence": "HIGH"},
    "PEPE": {"sectors": ["meme", "eth-ecosystem"], "confidence": "HIGH"},
    "WIF": {"sectors": ["meme", "sol-ecosystem"], "confidence": "HIGH"},
    "BONK": {"sectors": ["meme", "sol-ecosystem"], "confidence": "HIGH"},
    "FLOKI": {"sectors": ["meme"], "confidence": "MEDIUM"},
    "MEME": {"sectors": ["meme"], "confidence": "MEDIUM"},
    "POPCAT": {"sectors": ["meme", "sol-ecosystem"], "confidence": "MEDIUM"},
    "ONDO": {"sectors": ["rwa"], "confidence": "HIGH"},
    "POLYX": {"sectors": ["rwa"], "confidence": "MEDIUM"},
    "CFG": {"sectors": ["rwa"], "confidence": "MEDIUM"},
    "OM": {"sectors": ["rwa"], "confidence": "MEDIUM"},
    "AXS": {"sectors": ["gamefi"], "confidence": "HIGH"},
    "SAND": {"sectors": ["gamefi"], "confidence": "HIGH"},
    "MANA": {"sectors": ["gamefi"], "confidence": "HIGH"},
    "GALA": {"sectors": ["gamefi"], "confidence": "MEDIUM"},
    "IMX": {"sectors": ["gamefi", "layer2"], "confidence": "MEDIUM"},
    "PIXEL": {"sectors": ["gamefi"], "confidence": "MEDIUM"},
    "LINK": {"sectors": ["oracle", "infrastructure", "eth-ecosystem"], "confidence": "HIGH"},
    "PYTH": {"sectors": ["oracle", "sol-ecosystem"], "confidence": "HIGH"},
    "API3": {"sectors": ["oracle"], "confidence": "MEDIUM"},
    "BAND": {"sectors": ["oracle"], "confidence": "MEDIUM"},
    "FIL": {"sectors": ["storage", "depin", "infrastructure"], "confidence": "HIGH"},
    "AR": {"sectors": ["storage", "depin"], "confidence": "HIGH"},
    "STORJ": {"sectors": ["storage"], "confidence": "MEDIUM"},
    "HNT": {"sectors": ["depin"], "confidence": "HIGH"},
    "IOTX": {"sectors": ["depin"], "confidence": "MEDIUM"},
    "MOBILE": {"sectors": ["depin", "sol-ecosystem"], "confidence": "MEDIUM"},
    "ZEC": {"sectors": ["privacy"], "confidence": "HIGH"},
    "XMR": {"sectors": ["privacy"], "confidence": "HIGH"},
    "SCRT": {"sectors": ["privacy"], "confidence": "MEDIUM"},
    "W": {"sectors": ["interoperability"], "confidence": "MEDIUM"},
    "AXL": {"sectors": ["interoperability"], "confidence": "MEDIUM"},
    "STX": {"sectors": ["btc-ecosystem", "layer1"], "confidence": "HIGH"},
    "ORDI": {"sectors": ["btc-ecosystem", "meme"], "confidence": "MEDIUM"},
    "SATS": {"sectors": ["btc-ecosystem", "meme"], "confidence": "MEDIUM"},
    "RUNE": {"sectors": ["defi", "interoperability"], "confidence": "HIGH"},
    "ENS": {"sectors": ["eth-ecosystem", "infrastructure"], "confidence": "HIGH"},
    "GRT": {"sectors": ["infrastructure", "eth-ecosystem"], "confidence": "HIGH"},
    "ENA": {"sectors": ["defi", "eth-ecosystem"], "confidence": "MEDIUM"},
    "ETHFI": {"sectors": ["defi", "eth-ecosystem"], "confidence": "MEDIUM"},
    "EIGEN": {"sectors": ["infrastructure", "eth-ecosystem"], "confidence": "MEDIUM"},
    "JTO": {"sectors": ["sol-ecosystem", "liquid-staking"], "confidence": "MEDIUM"},
    "PYTHNET": {"sectors": ["oracle"], "confidence": "LOW"},
    "BCH": {"sectors": ["layer1", "btc-ecosystem"], "confidence": "HIGH"},
    "LTC": {"sectors": ["layer1"], "confidence": "HIGH"},
    "ETC": {"sectors": ["layer1"], "confidence": "HIGH"},
    "HYPE": {"sectors": ["defi", "dex"], "confidence": "MEDIUM"},
    "AERO": {"sectors": ["defi", "dex", "eth-ecosystem"], "confidence": "MEDIUM"},
    "VIRTUAL": {"sectors": ["ai"], "confidence": "MEDIUM"},
    "AI16Z": {"sectors": ["ai", "sol-ecosystem"], "confidence": "MEDIUM"},
    "GOAT": {"sectors": ["ai", "meme", "sol-ecosystem"], "confidence": "MEDIUM"},
    "FARTCOIN": {"sectors": ["meme", "sol-ecosystem"], "confidence": "MEDIUM"},
    "PNUT": {"sectors": ["meme", "sol-ecosystem"], "confidence": "MEDIUM"},
    "TRUMP": {"sectors": ["meme", "sol-ecosystem"], "confidence": "MEDIUM"},
    "MELANIA": {"sectors": ["meme"], "confidence": "LOW"},
    "SPX": {"sectors": ["meme"], "confidence": "MEDIUM"},
    "MOODENG": {"sectors": ["meme", "sol-ecosystem"], "confidence": "MEDIUM"},
    "MEW": {"sectors": ["meme", "sol-ecosystem"], "confidence": "MEDIUM"},
    "BOME": {"sectors": ["meme", "sol-ecosystem"], "confidence": "MEDIUM"},
    "NEIRO": {"sectors": ["meme"], "confidence": "MEDIUM"},
    "NOT": {"sectors": ["meme"], "confidence": "MEDIUM"},
    "HMSTR": {"sectors": ["gamefi", "meme"], "confidence": "MEDIUM"},
    "CATI": {"sectors": ["gamefi"], "confidence": "LOW"},
    "XAI": {"sectors": ["gamefi", "ai"], "confidence": "MEDIUM"},
    "PORTAL": {"sectors": ["gamefi"], "confidence": "MEDIUM"},
    "BEAM": {"sectors": ["gamefi"], "confidence": "MEDIUM"},
    "PRIME": {"sectors": ["gamefi"], "confidence": "MEDIUM"},
    "ALT": {"sectors": ["infrastructure", "interoperability"], "confidence": "MEDIUM"},
    "ZRO": {"sectors": ["interoperability"], "confidence": "HIGH"},
    "CKB": {"sectors": ["layer1", "btc-ecosystem"], "confidence": "MEDIUM"},
    "KAS": {"sectors": ["layer1"], "confidence": "MEDIUM"},
    "CFX": {"sectors": ["layer1"], "confidence": "MEDIUM"},
    "ICP": {"sectors": ["layer1", "infrastructure"], "confidence": "HIGH"},
    "FTM": {"sectors": ["layer1"], "confidence": "MEDIUM"},
    "S": {"sectors": ["layer1"], "confidence": "MEDIUM"},
    "BERA": {"sectors": ["layer1", "defi"], "confidence": "MEDIUM"},
    "MOVE": {"sectors": ["layer1"], "confidence": "MEDIUM"},
    "IP": {"sectors": ["rwa"], "confidence": "MEDIUM"},
}


def _strip_base(symbol: str) -> str:
    s = symbol.upper().strip()
    if s.endswith("USDT"):
        s = s[:-4]
    if s.startswith("1000"):
        s = s[4:]
    if s.startswith("1000000"):
        s = s[7:]
    return s


def list_sectors() -> list[dict[str, Any]]:
    return [dict(s) for s in sorted(SECTORS, key=lambda x: x["displayOrder"])]


def get_sector(sector_id_or_slug: str) -> dict[str, Any] | None:
    key = sector_id_or_slug.lower().strip()
    for s in SECTORS:
        if s["id"] == key or s["slug"] == key:
            return dict(s)
    return None


def membership_for_symbol(symbol: str) -> dict[str, Any]:
    raw = symbol.upper().strip()
    base = _strip_base(raw)
    meta = _MEMBERSHIPS.get(base)
    if not meta:
        return {
            "canonicalSymbol": f"{base}USDT",
            "exchangeSymbols": [raw],
            "sectorIds": [],
            "source": "NEXUS_CURATED",
            "confidence": "LOW",
            "classified": False,
            "base": base,
        }
    return {
        "canonicalSymbol": f"{base}USDT",
        "exchangeSymbols": list({raw, f"{base}USDT", f"1000{base}USDT"}),
        "sectorIds": list(meta["sectors"]),
        "source": "NEXUS_CURATED",
        "confidence": meta.get("confidence", "MEDIUM"),
        "classified": True,
        "base": base,
    }


def symbols_for_sector(sector_id: str) -> list[str]:
    sid = sector_id.lower().strip()
    out: list[str] = []
    for base, meta in _MEMBERSHIPS.items():
        if sid in meta["sectors"]:
            out.append(f"{base}USDT")
    return sorted(out)


def taxonomy_stats() -> dict[str, Any]:
    classified_bases = len(_MEMBERSHIPS)
    return {
        "sectorCount": len([s for s in SECTORS if s["id"] != "other"]),
        "classifiedBaseCount": classified_bases,
        "source": "NEXUS_CURATED",
        "multiMembership": True,
        "runtimeLlmClassification": False,
        "note": "Coverage is curated; unclassified markets remain Unclassified — not forced into Other for fake coverage.",
    }
