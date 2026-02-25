"""
News sentiment integration via Polygon.io (paid/real-time tier).

Provides:
  - get_market_headlines()    → broad market news for Macro Agent
  - get_batch_sentiment()     → per-ticker sentiment for Market Scanner Agent
  - get_ticker_sentiment()    → deep-dive sentiment for a single ticker

Polygon.io News API:
  GET /v2/reference/news
  Docs: https://polygon.io/docs/stocks/get_v2_reference_news
  Response includes `insights[]` with per-ticker sentiment:
    {ticker, sentiment: "positive|negative|neutral", sentiment_reasoning}
"""
import os
import requests
from typing import List, Dict, Optional
from dotenv import load_dotenv
from config.logging_config import get_logger

log = get_logger("tools.news_sentiment")

load_dotenv()

POLYGON_BASE_URL = "https://api.polygon.io"
_NO_KEY_WARNED = False  # warn once per process


def _get_api_key() -> Optional[str]:
    return os.getenv("POLYGON_API_KEY")


def _request(endpoint: str, params: Dict) -> Optional[Dict]:
    """Make a Polygon.io API request. Returns parsed JSON or None on failure."""
    global _NO_KEY_WARNED
    api_key = _get_api_key()
    if not api_key:
        if not _NO_KEY_WARNED:
            log.warning("[NewsSentiment] POLYGON_API_KEY not set — news context disabled.")
            print("[Polygon] WARNING: POLYGON_API_KEY not set — skipping news fetch.")
            _NO_KEY_WARNED = True
        return None

    display_params = {k: v for k, v in params.items() if k != "apiKey"}
    url = f"{POLYGON_BASE_URL}{endpoint}"
    log.info("[Polygon] GET %s params=%s", url, display_params)
    print(f"[Polygon] Fetching: GET {url}  params={display_params}")

    params["apiKey"] = api_key
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        count = len(data.get("results", []))
        log.info("[Polygon] Response: %d results (status=%s)", count, resp.status_code)
        print(f"[Polygon] Response: {count} articles returned (HTTP {resp.status_code})")
        return data
    except requests.exceptions.HTTPError as e:
        log.error("[Polygon] HTTP error %s: %s", e.response.status_code, e)
        print(f"[Polygon] ERROR: HTTP {e.response.status_code} — {e}")
        return None
    except Exception as e:
        log.error("[Polygon] Request failed: %s", e)
        print(f"[Polygon] ERROR: {e}")
        return None


def _parse_insights(insights: List[Dict], target_symbol: Optional[str] = None) -> Dict:
    """
    Aggregate Polygon insights[] into a sentiment summary.

    Args:
        insights: List of {ticker, sentiment, sentiment_reasoning} dicts.
        target_symbol: If set, only count insights for this ticker.

    Returns:
        {sentiment_score: float[-1,1], positive: int, negative: int, neutral: int, total: int}
    """
    counts = {"positive": 0, "negative": 0, "neutral": 0}
    for item in insights:
        if target_symbol and item.get("ticker", "").upper() != target_symbol.upper():
            continue
        s = item.get("sentiment", "neutral").lower()
        if s in counts:
            counts[s] += 1

    total = sum(counts.values())
    if total == 0:
        score = 0.0
    else:
        score = round((counts["positive"] - counts["negative"]) / total, 3)

    return {"sentiment_score": score, **counts, "total": total}


def _article_overall_sentiment(insights: List[Dict]) -> str:
    """Determine overall sentiment label for a single article."""
    pos = sum(1 for i in insights if i.get("sentiment") == "positive")
    neg = sum(1 for i in insights if i.get("sentiment") == "negative")
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


# ── Public API ────────────────────────────────────────────────────────────────

def get_market_headlines(limit: int = 15) -> List[Dict]:
    """
    Fetch broad market headlines from Polygon.io (no ticker filter).
    Used by the Macro Intelligence Agent for market-wide sentiment context.

    Returns:
        List of dicts: {title, published_utc, tickers, overall_sentiment}
    """
    data = _request("/v2/reference/news", {
        "limit": limit,
        "order": "desc",
        "sort": "published_utc",
    })
    if not data or "results" not in data:
        return []

    headlines = []
    for article in data["results"]:
        insights = article.get("insights", [])
        headlines.append({
            "title": article.get("title", ""),
            "published_utc": article.get("published_utc", "")[:16],
            "tickers": article.get("tickers", [])[:5],
            "overall_sentiment": _article_overall_sentiment(insights),
        })

    log.info("[Polygon] get_market_headlines: fetched %d headlines", len(headlines))
    print(f"\n[Polygon] Market Headlines ({len(headlines)} articles):")
    for h in headlines:
        print(f"  [{h['overall_sentiment'].upper():8s}] {h['published_utc']}  {h['title'][:80]}")
    print()

    return headlines


def get_batch_sentiment(symbols: List[str]) -> Dict[str, Dict]:
    """
    Fetch news and compute sentiment for a list of symbols in a single API call.
    Groups articles from the broad news feed by ticker via the `insights` field.

    Args:
        symbols: List of ticker symbols.

    Returns:
        Dict keyed by symbol (uppercase):
          {sentiment_score, positive, negative, neutral, total, headline_count, top_headlines}
    """
    if not symbols:
        return {}

    symbol_set = {s.upper() for s in symbols}

    # One broad call — more efficient than N per-ticker calls
    data = _request("/v2/reference/news", {
        "limit": 50,
        "order": "desc",
        "sort": "published_utc",
    })
    if not data or "results" not in data:
        return {s: _empty_sentiment() for s in symbol_set}

    # Collect per-ticker insights and titles
    ticker_insights: Dict[str, List] = {s: [] for s in symbol_set}
    ticker_titles: Dict[str, List] = {s: [] for s in symbol_set}
    ticker_article_count: Dict[str, int] = {s: 0 for s in symbol_set}

    for article in data["results"]:
        article_tickers = {t.upper() for t in article.get("tickers", [])}
        insights = article.get("insights", [])
        title = article.get("title", "")

        for symbol in symbol_set:
            if symbol in article_tickers:
                ticker_article_count[symbol] += 1
                if len(ticker_titles[symbol]) < 3:
                    ticker_titles[symbol].append(title)
                for insight in insights:
                    if insight.get("ticker", "").upper() == symbol:
                        ticker_insights[symbol].append(insight)

    result = {}
    for symbol in symbol_set:
        parsed = _parse_insights(ticker_insights[symbol])
        result[symbol] = {
            **parsed,
            "headline_count": ticker_article_count[symbol],
            "top_headlines": ticker_titles[symbol],
        }

    log.info("[Polygon] get_batch_sentiment: %s", {s: r["sentiment_score"] for s, r in result.items()})
    print(f"\n[Polygon] Batch Sentiment for {sorted(symbol_set)}:")
    for sym in sorted(result):
        r = result[sym]
        print(f"  {sym:6s}  score={r['sentiment_score']:+.2f}  "
              f"(+{r['positive']} -{r['negative']} ~{r['neutral']})  "
              f"articles={r['headline_count']}")
    print()

    return result


def get_ticker_sentiment(symbol: str, limit: int = 5) -> Dict:
    """
    Fetch news and sentiment for a single ticker via direct Polygon call.
    Useful when you need deeper coverage for a specific asset.

    Args:
        symbol: Ticker symbol.
        limit: Max number of articles to fetch.

    Returns:
        {sentiment_score, positive, negative, neutral, total, top_headlines}
    """
    data = _request("/v2/reference/news", {
        "ticker": symbol.upper(),
        "limit": limit,
        "order": "desc",
        "sort": "published_utc",
    })
    if not data or "results" not in data:
        return _empty_sentiment()

    all_insights = []
    headlines = []
    for article in data["results"]:
        headlines.append(article.get("title", ""))
        all_insights.extend(article.get("insights", []))

    parsed = _parse_insights(all_insights, target_symbol=symbol)
    parsed["top_headlines"] = headlines[:3]
    return parsed


def _empty_sentiment() -> Dict:
    return {
        "sentiment_score": 0.0,
        "positive": 0, "negative": 0, "neutral": 0, "total": 0,
        "headline_count": 0,
        "top_headlines": [],
    }
