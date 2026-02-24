"""
Live price fetching from yfinance for the dashboard.
Uses tuple args (not list) so Streamlit cache can hash the arguments.
30s TTL — shorter than DB queries (60s) since prices are time-sensitive.
"""
from typing import Optional
import streamlit as st
import yfinance as yf
import pandas as pd


@st.cache_data(ttl=30)
def fetch_live_prices(symbols: tuple) -> dict:
    """
    Batch-fetch current prices for all symbols in one yf.download() call.
    Falls back to per-ticker fetch on any failure.
    """
    result = {}
    if not symbols:
        return result

    try:
        data = yf.download(
            list(symbols),
            period="2d",
            interval="1d",
            auto_adjust=True,
            progress=False,
        )
        for sym in symbols:
            try:
                if isinstance(data.columns, pd.MultiIndex):
                    close = data["Close"][sym].dropna()
                else:
                    close = data["Close"].dropna()
                result[sym] = round(float(close.iloc[-1]), 4) if not close.empty else None
            except Exception:
                result[sym] = _single_price(sym)
    except Exception:
        for sym in symbols:
            result[sym] = _single_price(sym)

    return result


def _single_price(symbol: str) -> Optional[float]:
    """Fallback single-ticker price fetch."""
    try:
        t = yf.Ticker(symbol)
        p = t.fast_info.last_price
        return round(float(p), 4) if p else None
    except Exception:
        return None


@st.cache_data(ttl=30)
def fetch_spy_history_30d() -> list:
    """
    SPY daily closes for the last 30 trading days.
    Used for the benchmark line chart overlay.
    """
    try:
        hist = yf.Ticker("SPY").history(period="45d").tail(30)
        return [
            {"date": str(idx.date()), "close": round(float(row["Close"]), 4)}
            for idx, row in hist.iterrows()
        ]
    except Exception:
        return []
