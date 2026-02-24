"""
Section C: Benchmark Comparison.
Table: portfolio vs SPY/QQQ/DIA/IVV.
Line chart: portfolio cumulative return vs SPY (last 30 days).
"""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from dashboard.utils.theme import PLOTLY_LAYOUT, AXIS_STYLE, LEGEND_H, ACCENT, PROFIT_GREEN, LOSS_RED
from dashboard.utils.formatting import fmt_pct


def render_benchmark_comparison(
    portfolio_return: float,
    benchmarks: list,
    perf_history: list,
    spy_live_history: list,
):
    # ── Comparison Table (full width) ─────────────────────────────────────────
    st.markdown("#### vs Benchmarks (Today)")

    if benchmarks:
        rows = []
        for b in benchmarks:
            bret = b["return_pct"]
            diff = portfolio_return - bret
            rows.append({
                "Benchmark": b["symbol"],
                "Bench Return": fmt_pct(bret),
                "Portfolio": fmt_pct(portfolio_return),
                "Diff": fmt_pct(diff),
                "Result": "BEAT ▲" if diff >= 0 else "LAGGED ▼",
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.caption("No benchmark data (run --evaluate first).")

    # ── Line Chart (full width below table) ───────────────────────────────────
    st.markdown("#### Portfolio vs SPY — Last 30 Days")

    fig = go.Figure()

    # Portfolio cumulative return from DB history (last 30 rows)
    if perf_history:
        hist_df = pd.DataFrame(perf_history[-30:])
        hist_df["cumulative"] = hist_df["daily_return_pct"].cumsum()
        fig.add_trace(go.Scatter(
            x=hist_df["trade_date"],
            y=hist_df["cumulative"],
            name="Portfolio",
            line=dict(color=ACCENT, width=2),
            mode="lines+markers",
            marker=dict(size=5),
            hovertemplate="<b>%{x}</b><br>Portfolio: %{y:.4f}%<extra></extra>",
        ))

    # SPY from live yfinance
    if spy_live_history and len(spy_live_history) > 1:
        spy_df = pd.DataFrame(spy_live_history)
        spy_start = spy_df["close"].iloc[0]
        spy_df["spy_return"] = (spy_df["close"] - spy_start) / spy_start * 100
        fig.add_trace(go.Scatter(
            x=spy_df["date"],
            y=spy_df["spy_return"],
            name="SPY",
            line=dict(color="#8884d8", width=2, dash="dash"),
            mode="lines",
            hovertemplate="<b>%{x}</b><br>SPY: %{y:.4f}%<extra></extra>",
        ))

    fig.add_hline(y=0, line_color="rgba(255,255,255,0.15)", line_width=1)
    fig.update_layout(
        **PLOTLY_LAYOUT,
        height=220,
        yaxis_ticksuffix="%",
        legend=LEGEND_H,
    )
    fig.update_xaxes(**AXIS_STYLE)
    fig.update_yaxes(**AXIS_STYLE)
    st.plotly_chart(fig, use_container_width=True)
