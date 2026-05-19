import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


class NewsIngestionService:
    FEEDS = [
        ("加密新聞牆", "crypto", "https://news.google.com/rss/search?q=cryptocurrency+OR+bitcoin+OR+ethereum+OR+solana+OR+bnb&hl=en-US&gl=US&ceid=US:en"),
        ("比特幣", "crypto", "https://news.google.com/rss/search?q=bitcoin+when:1d&hl=en-US&gl=US&ceid=US:en"),
        ("乙太坊", "crypto", "https://news.google.com/rss/search?q=ethereum+when:1d&hl=en-US&gl=US&ceid=US:en"),
        ("Solana", "crypto", "https://news.google.com/rss/search?q=solana+crypto+when:1d&hl=en-US&gl=US&ceid=US:en"),
        ("BNB", "crypto", "https://news.google.com/rss/search?q=bnb+crypto+when:1d&hl=en-US&gl=US&ceid=US:en"),
        ("宏觀數據牆", "macro", "https://news.google.com/rss/search?q=CPI+OR+PCE+OR+GDP+OR+jobs+OR+inflation+OR+treasury+macro+when:2d&hl=en-US&gl=US&ceid=US:en"),
        ("聯準會中樞", "fed", "https://news.google.com/rss/search?q=Fed+OR+FOMC+OR+Powell+OR+rate+cut+OR+rate+hike+OR+SEC+crypto+ETF+when:2d&hl=en-US&gl=US&ceid=US:en"),
        ("聯準會官方", "fed", "https://www.federalreserve.gov/feeds/press_monetary.xml"),
    ]

    MAJOR_KEYWORDS = {
        "etf", "sec", "fed", "fomc", "lawsuit", "hack", "bankruptcy", "liquidation",
        "tariff", "cpi", "rate", "ban", "approve", "approval", "breaking", "urgent",
        "whale", "blackrock", "coinbase", "binance", "treasury", "war", "sanction",
    }
    PAUSE_KEYWORDS = {
        "hack", "lawsuit", "ban", "bankruptcy", "liquidation",
        "war", "sanction", "exploit", "breach", "insolvency", "halt",
    }
    POSITIVE_KEYWORDS = {"surge", "approve", "approval", "rally", "gain", "bull", "record", "launch", "buy", "inflow"}
    NEGATIVE_KEYWORDS = {"drop", "fall", "hack", "lawsuit", "ban", "selloff", "outflow", "liquidation", "delay", "warning"}
    TARGET_KEYWORDS = {
        "BTC": {"bitcoin", "btc"},
        "ETH": {"ethereum", "eth"},
        "SOL": {"solana", "sol"},
        "BNB": {"bnb", "binance coin"},
        "PEPE": {"pepe"},
    }

    def __init__(self, timeout=12, refresh_seconds=180):
        self.timeout = timeout
        self.refresh_seconds = refresh_seconds
        self._cache = []
        self._cache_at = 0.0
        self._translation_cache = {}

    def latest(self, limit=24):
        import time

        if self._cache and time.time() - self._cache_at < self.refresh_seconds:
            return self._cache[:limit]

        bucketed = {"macro": [], "fed": [], "crypto": []}
        seen = set()
        for category, bucket, url in self.FEEDS:
            try:
                bucketed.setdefault(bucket, []).extend(self._fetch_feed(category, bucket, url, seen))
            except Exception:
                continue

        items = []
        per_bucket_limit = max(4, limit // 3)
        for bucket in ("macro", "fed", "crypto"):
            bucket_rows = bucketed.get(bucket, [])
            bucket_rows.sort(key=lambda item: item.get("published_ts", ""), reverse=True)
            items.extend(bucket_rows[:per_bucket_limit])

        items.sort(key=lambda item: item.get("published_ts", ""), reverse=True)
        cleaned = items[:limit]
        self._cache = cleaned
        self._cache_at = time.time()
        return cleaned

    def _fetch_feed(self, category, bucket, url, seen):
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        root = ET.fromstring(urlopen(request, timeout=self.timeout).read())
        rows = []
        for item in root.findall("./channel/item")[:16]:
            title = self._text(item.findtext("title"))
            link = self._text(item.findtext("link"))
            pub_date = self._text(item.findtext("pubDate"))
            source = category
            guid = self._text(item.findtext("guid")) or f"{title}|{link}"
            if guid in seen or not title:
                continue
            seen.add(guid)
            title_zh = self._translate_text(title)
            targets = self._detect_targets(title)
            sentiment = self._detect_sentiment(title)
            impact = self._detect_impact(title)
            rows.append({
                "id": guid,
                "time": self._format_time(pub_date),
                "published_ts": self._format_timestamp(pub_date),
                "title": title,
                "title_zh": title_zh,
                "summary": title,
                "summary_zh": title_zh,
                "targets": targets,
                "tone": sentiment.lower(),
                "sentiment": sentiment,
                "impact": impact,
                "major": self._is_major_pause_candidate(title, impact, bucket, sentiment),
                "category": category,
                "bucket": bucket,
                "source": source,
                "link": link,
                "recommendation": self._recommendation(sentiment, impact, bucket),
            })
        return rows

    def _translate_text(self, text):
        if not text:
            return ""
        if text in self._translation_cache:
            return self._translation_cache[text]
        try:
            endpoint = (
                "https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=zh-TW&dt=t&q="
                + quote(text)
            )
            payload = json.loads(urlopen(endpoint, timeout=self.timeout).read().decode("utf-8"))
            translated = "".join(part[0] for part in payload[0] if part and part[0])
        except Exception:
            translated = text
        self._translation_cache[text] = translated
        return translated

    def _detect_targets(self, text):
        lower = text.lower()
        targets = [symbol for symbol, keywords in self.TARGET_KEYWORDS.items() if any(word in lower for word in keywords)]
        return targets or ["ALL"]

    def _detect_sentiment(self, text):
        lower = text.lower()
        positive = sum(1 for word in self.POSITIVE_KEYWORDS if word in lower)
        negative = sum(1 for word in self.NEGATIVE_KEYWORDS if word in lower)
        if negative > positive:
            return "NEGATIVE"
        if positive > negative:
            return "POSITIVE"
        return "NEUTRAL"

    def _detect_impact(self, text):
        lower = text.lower()
        if any(word in lower for word in self.MAJOR_KEYWORDS):
            return "HIGH"
        if any(symbol in lower for symbol in ("bitcoin", "ethereum", "solana", "bnb", "pepe")):
            return "MEDIUM"
        return "LOW"

    def _recommendation(self, sentiment, impact, bucket):
        if bucket == "macro":
            return "宏觀資料更新後，先觀察外部市場與風險資產是否同步轉向，再決定是否提高風險曝險。"
        if bucket == "fed":
            return "聯準會與政策資訊更新後，優先重新評估利率敏感資產與市場風險偏好。"
        if impact == "HIGH":
            return "重大情報已進場，先交由總部與風控重新評估，再決定是否擴大或縮小部位。"
        if sentiment == "POSITIVE":
            return "偏多新聞，觀察是否帶動主流幣與高 Beta 幣種延續上行。"
        if sentiment == "NEGATIVE":
            return "偏空新聞，觀察是否引發主流幣轉弱與流動性退潮。"
        return "資訊中性，持續監控後續市場反應與資金輪動。"

    def _is_major_pause_candidate(self, text, impact, bucket, sentiment):
        if impact != "HIGH":
            return False
        if bucket == "macro":
            return False
        lower = text.lower()
        if any(word in lower for word in ("price breaks", "breakout", "surge", "record", "rally", "approval", "approve")):
            return False
        if sentiment == "POSITIVE" and ("breakout" in lower or "surge" in lower or "record" in lower):
            return False
        return any(word in lower for word in self.PAUSE_KEYWORDS)

    @staticmethod
    def _text(value):
        return re.sub(r"\s+", " ", (value or "").strip())

    @staticmethod
    def _format_time(pub_date):
        try:
            dt = parsedate_to_datetime(pub_date)
            return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _format_timestamp(pub_date):
        try:
            dt = parsedate_to_datetime(pub_date)
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            return datetime.now(timezone.utc).isoformat()
