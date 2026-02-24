"""
Risk metric calculations: Sharpe ratio and max drawdown.
"""
import numpy as np
import pandas as pd
from typing import Union, Dict


def calculate_sharpe(
    returns: Union[pd.Series, list],
    risk_free_rate: float = 0.05,
    periods_per_year: int = 252
) -> float:
    """
    Annualized Sharpe ratio.

    Args:
        returns: Daily return series (decimal, e.g. 0.01 for 1%)
        risk_free_rate: Annual risk-free rate (default 5%)
        periods_per_year: Trading days per year

    Returns:
        Annualized Sharpe ratio, or 0.0 if insufficient data.
    """
    if isinstance(returns, list):
        returns = pd.Series(returns)

    if len(returns) < 2:
        return 0.0

    daily_rf = risk_free_rate / periods_per_year
    excess = returns - daily_rf
    std = excess.std()

    if std == 0:
        return 0.0

    sharpe = (excess.mean() / std) * np.sqrt(periods_per_year)
    return round(float(sharpe), 4)


def calculate_drawdown(returns: Union[pd.Series, list]) -> Dict[str, float]:
    """
    Calculate max drawdown and current drawdown from a return series.

    Args:
        returns: Daily return series (decimal)

    Returns:
        {max_drawdown: float, current_drawdown: float}
        Values are negative (e.g. -0.05 = -5% drawdown)
    """
    if isinstance(returns, list):
        returns = pd.Series(returns)

    if len(returns) < 2:
        return {"max_drawdown": 0.0, "current_drawdown": 0.0}

    cumulative = (1 + returns).cumprod()
    rolling_max = cumulative.cummax()
    drawdown = (cumulative - rolling_max) / rolling_max

    max_dd = float(drawdown.min())
    current_dd = float(drawdown.iloc[-1])

    return {
        "max_drawdown": round(max_dd, 4),
        "current_drawdown": round(current_dd, 4),
    }
