"""
Section B: Daily Summary Header.
Macro bias / risk env / strategy badges + 4 key metrics.
"""
from typing import Optional
import streamlit as st
from dashboard.utils.formatting import fmt_dollars, fmt_pct, bias_color, risk_env_color
from dashboard.utils.theme import ACCENT, TEXT_MUTED


def _badge(label: str, color: str) -> str:
    return (
        f'<span style="background:{color}22;color:{color};'
        f'border:1px solid {color};border-radius:4px;'
        f'padding:3px 10px;font-size:11px;font-weight:700;">'
        f'{label}</span>'
    )


def render_daily_summary(trading_day: Optional[dict], performance: Optional[dict]):
    if not trading_day:
        st.warning("No trading day found. Click 'Run Daily' in the sidebar to start.")
        return

    col_date, col_bias, col_env, col_strat, _ = st.columns([2, 1, 1, 1, 2])

    with col_date:
        st.markdown(f"### {trading_day['trade_date']}")

    with col_bias:
        bias = trading_day.get("macro_bias") or "N/A"
        st.html(_badge(bias.upper(), bias_color(bias)))
        st.caption("Macro Bias")

    with col_env:
        env = trading_day.get("risk_environment") or "N/A"
        st.html(_badge(env.upper(), risk_env_color(env)))
        st.caption("Risk Env")

    with col_strat:
        strat = trading_day.get("strategy_type") or "N/A"
        st.html(_badge(strat.upper(), ACCENT))
        st.caption("Strategy")

    st.divider()

    capital = trading_day.get("total_capital", 100.0)
    m1, m2, m3, m4 = st.columns(4)

    with m1:
        st.metric("Total Invested", fmt_dollars(capital))

    if performance:
        pv  = performance.get("portfolio_value", 0)
        pnl = performance.get("daily_profit_loss", 0)
        ret = performance.get("daily_return_pct", 0)

        with m2:
            st.metric("Portfolio Value", fmt_dollars(pv), delta=fmt_dollars(pnl))
        with m3:
            st.metric("Total P/L", fmt_dollars(pnl), delta=fmt_pct(ret))
        with m4:
            st.metric("Return Today", fmt_pct(ret))
    else:
        for col in (m2, m3, m4):
            with col:
                st.metric("—", "Run --evaluate")
