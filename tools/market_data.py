"""
Market data tools powered by yfinance.
All prices are real - never hallucinated.
"""
import yfinance as yf
import pandas as pd
from typing import List, Dict, Optional

# Benchmark ETFs — used ONLY for performance comparison, never for investment selection
BENCHMARK_SYMBOLS = ["SPY", "QQQ", "DIA", "IVV"]

# S&P 500 large-cap sample for movers scan (investment candidates)
SP500_SAMPLE = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "BRK-B",
    "JPM", "UNH", "V", "XOM", "LLY", "JNJ", "AVGO", "PG", "MA", "COST",
    "HD", "MRK", "ABBV", "CVX", "WMT", "BAC", "KO", "PFE", "AMD", "ADBE",
    "CRM", "TMO", "NFLX", "DIS", "CSCO", "ABT", "ACN", "MCD", "NEE", "RTX",
    "CAT", "GE", "HON", "IBM", "INTC", "GS", "ORCL", "QCOM", "TXN", "AMGN"
]

# Defensive large-caps used when VIX > 25 (consumer staples, healthcare, utilities)
DEFENSIVE_STOCKS = [
    # Consumer Staples
    "PG", "KO", "PEP", "WMT", "COST", "MDLZ", "CL", "GIS",
    # Healthcare
    "JNJ", "UNH", "PFE", "ABBV", "MRK", "TMO", "ABT", "BMY",
    # Utilities
    "NEE", "DUK", "SO", "D", "AEP",
]


def _safe_price(ticker: yf.Ticker) -> Optional[float]:
    """Safely retrieve the last price from a yfinance ticker."""
    try:
        price = ticker.fast_info.last_price
        return round(float(price), 4) if price else None
    except Exception:
        return None


def _momentum_score(hist: pd.DataFrame) -> float:
    """Calculate 30-day momentum score (0-1)."""
    if hist.empty or len(hist) < 5:
        return 0.5
    ret = (hist["Close"].iloc[-1] - hist["Close"].iloc[0]) / hist["Close"].iloc[0]
    # Normalize: -20% → 0, 0% → 0.5, +20% → 1
    score = min(max((ret + 0.20) / 0.40, 0.0), 1.0)
    return round(score, 3)


def _volatility_score(hist: pd.DataFrame) -> float:
    """Calculate 30-day volatility score (0-1). Higher = more volatile."""
    if hist.empty or len(hist) < 5:
        return 0.5
    daily_returns = hist["Close"].pct_change().dropna()
    vol = daily_returns.std() * (252 ** 0.5)  # annualized
    # Normalize: 0% → 0, 50%+ annualized vol → 1
    score = min(vol / 0.50, 1.0)
    return round(score, 3)


def get_top_movers(n: int = 10) -> List[Dict]:
    """
    Scan S&P 500 sample and return top gainers and losers by 5-day return.
    Returns at most n assets, no penny stocks (price < $5).
    """
    results = []
    tickers = yf.download(
        SP500_SAMPLE, period="10d", interval="1d",
        group_by="ticker", auto_adjust=True, progress=False
    )

    for symbol in SP500_SAMPLE:
        try:
            if isinstance(tickers.columns, pd.MultiIndex):
                close = tickers[symbol]["Close"].dropna()
                volume = tickers[symbol]["Volume"].dropna()
            else:
                close = tickers["Close"].dropna()
                volume = tickers["Volume"].dropna()

            if len(close) < 2:
                continue

            price = float(close.iloc[-1])
            if price < 5:  # skip penny stocks
                continue

            # Liquidity filter: require avg daily traded value >= $50M
            avg_vol = float(volume.mean()) if len(volume) > 0 else 0
            avg_daily_value = price * avg_vol
            if avg_daily_value < 50_000_000:
                continue

            ret_5d = (close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] if len(close) >= 5 else 0
            results.append({
                "symbol": symbol,
                "asset_type": "stock",
                "price": round(price, 2),
                "return_5d": round(float(ret_5d), 4),
                "momentum_score": round(min(max((float(ret_5d) + 0.10) / 0.20, 0), 1), 3),
                "volatility_score": 0.5,  # placeholder; full calc needs more history
                "avg_daily_value_m": round(avg_daily_value / 1_000_000, 1),  # millions
            })
        except Exception:
            continue

    results.sort(key=lambda x: abs(x["return_5d"]), reverse=True)
    return results[:n]


def get_defensive_stocks(n: int = 15) -> List[Dict]:
    """
    Return defensive large-cap stocks for use in high-VIX / defensive mode.
    Pulls from consumer staples, healthcare, and utilities sectors.
    """
    results = []
    tickers = yf.download(
        DEFENSIVE_STOCKS, period="10d", interval="1d",
        group_by="ticker", auto_adjust=True, progress=False
    )

    for symbol in DEFENSIVE_STOCKS:
        try:
            if isinstance(tickers.columns, pd.MultiIndex):
                close = tickers[symbol]["Close"].dropna()
                volume = tickers[symbol]["Volume"].dropna()
            else:
                close = tickers["Close"].dropna()
                volume = tickers["Volume"].dropna()

            if len(close) < 2:
                continue

            price = float(close.iloc[-1])
            if price < 5:
                continue

            avg_vol = float(volume.mean()) if len(volume) > 0 else 0
            avg_daily_value = price * avg_vol
            if avg_daily_value < 10_000_000:
                continue

            ret_5d = (close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] if len(close) >= 5 else 0
            results.append({
                "symbol": symbol,
                "asset_type": "stock",
                "price": round(price, 2),
                "return_5d": round(float(ret_5d), 4),
                "momentum_score": round(min(max((float(ret_5d) + 0.10) / 0.20, 0), 1), 3),
                "volatility_score": 0.3,  # defensive stocks carry lower vol by nature
                "avg_daily_value_m": round(avg_daily_value / 1_000_000, 1),
            })
        except Exception:
            continue

    results.sort(key=lambda x: x["avg_daily_value_m"], reverse=True)
    return results[:n]


def get_current_price(symbol: str) -> Optional[float]:
    """
    Get the current last price for a symbol via yfinance.
    Returns None if unavailable — never guesses.
    """
    try:
        ticker = yf.Ticker(symbol)
        price = _safe_price(ticker)
        return price
    except Exception:
        return None


def get_historical_data(symbol: str, period: str = "30d") -> pd.DataFrame:
    """Return OHLCV DataFrame for a symbol."""
    try:
        ticker = yf.Ticker(symbol)
        return ticker.history(period=period)
    except Exception:
        return pd.DataFrame()


def get_benchmark_data() -> Dict[str, Dict]:
    """
    Return today's return for each benchmark vs yesterday.
    Used by Performance Agent.
    """
    results = {}
    for symbol in BENCHMARK_SYMBOLS:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="5d")
            if len(hist) >= 2:
                ret = (hist["Close"].iloc[-1] - hist["Close"].iloc[-2]) / hist["Close"].iloc[-2]
                results[symbol] = {
                    "price": round(float(hist["Close"].iloc[-1]), 2),
                    "return_pct": round(float(ret) * 100, 4),
                }
        except Exception:
            results[symbol] = {"price": None, "return_pct": None}
    return results


def get_vix() -> Optional[float]:
    """Get current VIX level. Used by VIXGuard."""
    try:
        ticker = yf.Ticker("^VIX")
        price = _safe_price(ticker)
        return price
    except Exception:
        return None
