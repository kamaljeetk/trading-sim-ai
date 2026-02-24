"""
Section G: Historical Performance Tab.
Cumulative+daily return combo chart, strategy summary table, daily sessions table.
"""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from dashboard.utils.theme import PLOTLY_LAYOUT, AXIS_STYLE, LEGEND_H, ACCENT, PROFIT_GREEN, LOSS_RED
from dashboard.utils.formatting import fmt_pct, fmt_dollars


def render_historical_tab(perf_history: list, strategy_summary: list, stats: dict):

    # ── Stats Row ──────────────────────────────────────────────────────────────
    s1, s2, s3, s4, s5 = st.columns(5)
    with s1:
        st.metric("Total Sessions", stats.get("total_days", 0))
    with s2:
        wr = stats.get("win_rate", 0)
        st.metric("Win Rate", f"{wr:.1f}%", delta="≥50%" if wr >= 50 else "<50%")
    with s3:
        st.metric("Avg Daily Return", fmt_pct(stats.get("avg_daily_return", 0), 4))
    with s4:
        st.metric("Best Day", fmt_pct(stats.get("best_day", 0), 4))
    with s5:
        st.metric("Worst Day", fmt_pct(stats.get("worst_day", 0), 4))

    st.divider()

    # ── Combo Chart ────────────────────────────────────────────────────────────
    if perf_history:
        df = pd.DataFrame(perf_history)
        df["cumulative"] = df["daily_return_pct"].cumsum()
        bar_colors = [PROFIT_GREEN if v >= 0 else LOSS_RED for v in df["daily_return_pct"]]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df["trade_date"],
            y=df["daily_return_pct"],
            name="Daily Return",
            marker_color=bar_colors,
            opacity=0.45,
            yaxis="y2",
            hovertemplate="<b>%{x}</b><br>Daily: %{y:.4f}%<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=df["trade_date"],
            y=df["cumulative"],
            name="Cumulative Return",
            line=dict(color=ACCENT, width=2.5),
            mode="lines",
            hovertemplate="<b>%{x}</b><br>Cumulative: %{y:.4f}%<extra></extra>",
        ))
        fig.update_layout(
            **PLOTLY_LAYOUT,
            height=370,
            title=dict(text="Cumulative vs Daily Returns", font=dict(size=14)),
            yaxis=dict(ticksuffix="%", title="Cumulative Return %"),
            yaxis2=dict(
                ticksuffix="%",
                title="Daily Return %",
                overlaying="y",
                side="right",
                showgrid=False,
            ),
            legend=LEGEND_H,
            barmode="overlay",
        )
        fig.update_xaxes(**AXIS_STYLE)
        fig.update_yaxes(**AXIS_STYLE)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No performance history yet.")

    # ── Strategy Summary Table ─────────────────────────────────────────────────
    if strategy_summary:
        st.markdown("#### Strategy Performance Summary")
        strat_df = pd.DataFrame(strategy_summary)
        st.dataframe(
            strat_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "strategy_name":    st.column_config.TextColumn("Strategy"),
                "cumulative_return":st.column_config.NumberColumn("Cumul. Return %", format="%.4f"),
                "avg_daily_return": st.column_config.NumberColumn("Avg Daily %",     format="%.4f"),
                "sharpe_ratio":     st.column_config.NumberColumn("Sharpe",          format="%.4f"),
                "max_drawdown":     st.column_config.NumberColumn("Max DD",          format="%.4f"),
                "volatility":       st.column_config.NumberColumn("Volatility",      format="%.4f"),
            },
        )

    # ── All Sessions Table ─────────────────────────────────────────────────────
    if perf_history:
        st.markdown("#### All Trading Sessions")
        display_df = pd.DataFrame(perf_history)[[
            "trade_date", "strategy_type", "macro_bias",
            "portfolio_value", "daily_profit_loss", "daily_return_pct",
            "sharpe_ratio", "max_drawdown",
        ]]
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "trade_date":       st.column_config.TextColumn("Date"),
                "strategy_type":    st.column_config.TextColumn("Strategy"),
                "macro_bias":       st.column_config.TextColumn("Bias"),
                "portfolio_value":  st.column_config.NumberColumn("Value",   format="$%.2f"),
                "daily_profit_loss":st.column_config.NumberColumn("P/L",     format="$%.2f"),
                "daily_return_pct": st.column_config.NumberColumn("Return %",format="%.4f"),
                "sharpe_ratio":     st.column_config.NumberColumn("Sharpe",  format="%.4f"),
                "max_drawdown":     st.column_config.NumberColumn("Max DD",  format="%.4f"),
            },
        )
