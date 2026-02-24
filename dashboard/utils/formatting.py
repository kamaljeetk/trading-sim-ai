"""
Financial display formatting utilities.
"""
from typing import Optional


def fmt_dollars(value: Optional[float], decimals: int = 2) -> str:
    """Format as $1,234.56 or -$1,234.56"""
    if value is None:
        return "N/A"
    v = float(value)
    sign = "-" if v < 0 else ""
    return f"{sign}${abs(v):,.{decimals}f}"


def fmt_pct(value: Optional[float], decimals: int = 2) -> str:
    """Format as +1.23% or -1.23%"""
    if value is None:
        return "N/A"
    v = float(value)
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.{decimals}f}%"


def pnl_color(value: Optional[float]) -> str:
    """Return hex color for a P&L value."""
    if value is None:
        return "#888888"
    from dashboard.utils.theme import PROFIT_GREEN, LOSS_RED
    return PROFIT_GREEN if float(value) >= 0 else LOSS_RED


def bias_color(bias: Optional[str]) -> str:
    """Color for macro bias badge."""
    from dashboard.utils.theme import PROFIT_GREEN, LOSS_RED, WARNING_YELLOW
    mapping = {
        "bullish": PROFIT_GREEN,
        "bearish": LOSS_RED,
        "neutral": WARNING_YELLOW,
    }
    return mapping.get(bias or "", "#888888")


def risk_env_color(env: Optional[str]) -> str:
    """Color for risk environment badge."""
    from dashboard.utils.theme import PROFIT_GREEN, LOSS_RED, WARNING_YELLOW
    mapping = {
        "risk_on":  PROFIT_GREEN,
        "risk_off": LOSS_RED,
        "mixed":    WARNING_YELLOW,
    }
    return mapping.get(env or "", "#888888")
