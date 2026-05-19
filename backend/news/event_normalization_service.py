import hashlib


class EventNormalizationService:
    EVENT_TYPE_KEYWORDS = {
        "fed_policy": {"fomc", "powell", "fed", "rate cut", "rate hike"},
        "macro_data": {"cpi", "pce", "inflation", "jobs", "gdp", "treasury"},
        "regulation": {"sec", "lawsuit", "etf", "approval", "ban"},
        "security_incident": {"hack", "exploit", "breach", "insolvency", "bankruptcy"},
        "exchange_risk": {"liquidation", "halt", "outflow", "delist"},
        "market_momentum": {"surge", "breakout", "record", "rally", "selloff", "drop"},
    }

    def normalize(self, analyzed_news):
        normalized = []
        for item in analyzed_news or []:
            summary = item.get("summary") or item.get("title") or ""
            lowered = summary.lower()
            event_type = "general_crypto"
            for candidate, keywords in self.EVENT_TYPE_KEYWORDS.items():
                if any(keyword in lowered for keyword in keywords):
                    event_type = candidate
                    break

            impact = str(item.get("impact") or "LOW").upper()
            sentiment = str(item.get("sentiment") or "NEUTRAL").upper()
            targets = list(item.get("targets") or ["ALL"])
            quality_score = 0.55
            if item.get("source"):
                quality_score += 0.1
            if impact == "HIGH":
                quality_score += 0.15
            if targets and targets != ["ALL"]:
                quality_score += 0.05
            if item.get("bucket") in {"fed", "macro"}:
                quality_score += 0.1
            quality_score = max(0.0, min(1.0, quality_score))

            normalized.append(
                {
                    "event_id": item.get("id") or self._fallback_id(summary),
                    "event_type": event_type,
                    "bucket": item.get("bucket", "crypto"),
                    "impact": impact,
                    "sentiment": sentiment,
                    "targets": targets,
                    "summary": item.get("summary_zh") or summary,
                    "source": item.get("source") or item.get("category") or "",
                    "major": bool(item.get("major")),
                    "quality_score": round(quality_score, 4),
                    "published_ts": item.get("published_ts") or "",
                    "link": item.get("link") or "",
                }
            )
        return normalized

    @staticmethod
    def _fallback_id(text):
        return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]

