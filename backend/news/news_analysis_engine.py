class NewsAnalysisEngine:
    def analyze(self, news_items):
        analyzed = []
        for item in news_items:
            sentiment = str(item.get("sentiment") or item.get("tone") or "NEUTRAL").upper()
            impact = str(item.get("impact") or "LOW").upper()
            if impact == "HIGH":
                recommendation = "重大情報，建議總部先暫停交易並召集圓桌討論。"
            elif sentiment == "POSITIVE":
                recommendation = "偏多新聞，交由各單位評估是否順勢布局。"
            elif sentiment == "NEGATIVE":
                recommendation = "偏空新聞，交由各單位評估是否降槓桿或等待確認。"
            else:
                recommendation = "中性新聞，維持監控並等待更多訊號。"
            analyzed.append({
                **item,
                "sentiment": sentiment,
                "impact": impact,
                "summary": item.get("summary_zh") or item.get("summary") or item.get("title_zh") or item.get("title", ""),
                "recommendation": item.get("recommendation") or recommendation,
            })
        return analyzed
