import { useEffect, useRef } from "react";

const TRADINGVIEW_SYMBOLS: Record<string, string> = {
  BTC: "BINANCE:BTCUSDT",
  BTCUSDT: "BINANCE:BTCUSDT",
  ETH: "BINANCE:ETHUSDT",
  ETHUSDT: "BINANCE:ETHUSDT",
  SOL: "BINANCE:SOLUSDT",
  SOLUSDT: "BINANCE:SOLUSDT",
};

function tradingViewSymbol(symbol?: string) {
  const normalized = (symbol || "").toUpperCase();
  return TRADINGVIEW_SYMBOLS[normalized] || (normalized.endsWith("USDT") ? `BINANCE:${normalized}` : undefined);
}

export function TradingViewTopStories({ symbol, title }: { symbol?: string; title: string }) {
  const container = useRef<HTMLDivElement>(null);
  const tvSymbol = tradingViewSymbol(symbol);
  const newsFlow = tvSymbol
    ? `https://www.tradingview.com/news/?symbol=${encodeURIComponent(tvSymbol)}`
    : "https://www.tradingview.com/news/";

  useEffect(() => {
    const node = container.current;
    if (!node) return;
    node.replaceChildren();
    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-timeline.js";
    script.async = true;
    script.textContent = JSON.stringify({
      feedMode: tvSymbol ? "symbol" : "market",
      symbol: tvSymbol,
      colorTheme: "light",
      isTransparent: true,
      displayMode: "regular",
      locale: "zh_TW",
      width: "100%",
      height: 480,
    });
    node.appendChild(script);
    return () => node.replaceChildren();
  }, [tvSymbol]);

  return (
    <article className="mpv1-card" data-classification="LIVE_TRADINGVIEW">
      <div className="mpv1-card-head">
        <div>
          <h2 className="mpv1-card-title">{title}</h2>
          <p className="mpv1-muted" style={{ fontSize: "0.75rem", margin: "0.25rem 0 0" }}>
            LIVE_TRADINGVIEW · 官方 Top Stories
          </p>
        </div>
        <a className="mpv1-action-link" href={newsFlow} target="_blank" rel="noreferrer">
          查看更多新聞 →
        </a>
      </div>
      <div className="tradingview-widget-container" ref={container}>
        <div className="tradingview-widget-container__widget" />
        <div className="tradingview-widget-copyright">
          <a href="https://www.tradingview.com/" rel="noreferrer" target="_blank">
            <span className="blue-text">TradingView</span>
          </a>
        </div>
      </div>
    </article>
  );
}
