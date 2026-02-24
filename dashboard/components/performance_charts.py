"""
Section D: Performance Charts.
1. Portfolio value over time (all sessions)
2. Cumulative return chart
3. Allocation pie chart (today)
"""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from dashboard.utils.theme import PLOTLY_LAYOUT, AXIS_STYLE, ACCENT, PROFIT_GREEN, LOSS_RED, PIE_COLORS


def render_performance_charts(perf_history: list, positions: list):

    # ── Chart 1: Portfolio Value (full width) ─────────────────────────────────
    st.markdown("#### Portfolio Value Over Time")
    if perf_history:
        df = pd.DataFrame(perf_history)
        colors = [PROFIT_GREEN if v >= 0 else LOSS_RED for v in df["daily_profit_loss"]]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["trade_date"],
            y=df["portfolio_value"],
            mode="lines+markers",
            name="Portfolio Value",
            line=dict(color=ACCENT, width=2),
            marker=dict(color=colors, size=8, line=dict(color="rgba(255,255,255,0.2)", width=1)),
            hovertemplate="<b>%{x}</b><br>Value: $%{y:.2f}<extra></extra>",
        ))
        fig.add_hline(
            y=100, line_color="rgba(255,255,255,0.25)",
            line_dash="dot",
            annotation_text="$100 baseline",
            annotation_font_color="rgba(255,255,255,0.4)",
            annotation_position="bottom right",
        )
        fig.update_layout(**PLOTLY_LAYOUT, height=220, yaxis_tickprefix="$")
        fig.update_xaxes(**AXIS_STYLE)
        fig.update_yaxes(**AXIS_STYLE)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No performance history yet.")

    # ── Row 2: Cumulative Return + Allocation Pie side by side ─────────────────
    row2_left, row2_right = st.columns([2, 1])

    with row2_left:
        st.markdown("#### Cumulative Return (All Sessions)")
        if perf_history:
            df = pd.DataFrame(perf_history)
            df["cumulative"] = df["daily_return_pct"].cumsum()

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df["trade_date"],
                y=df["cumulative"],
                fill="tozeroy",
                fillcolor="rgba(0,212,170,0.08)",
                line=dict(color=ACCENT, width=2),
                name="Cumulative Return",
                hovertemplate="<b>%{x}</b><br>%{y:.4f}%<extra></extra>",
            ))
            fig.add_hline(y=0, line_color="rgba(255,255,255,0.2)", line_width=1)
            fig.update_layout(**PLOTLY_LAYOUT, height=220, yaxis_ticksuffix="%")
            fig.update_xaxes(**AXIS_STYLE)
            fig.update_yaxes(**AXIS_STYLE)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Run more simulations to see cumulative performance.")

    with row2_right:
        st.markdown("#### Today's Allocation")
        if positions:
            fig = go.Figure(go.Pie(
                labels=[p["symbol"] for p in positions],
                values=[p["allocation_dollars"] for p in positions],
                hole=0.45,
                textinfo="label+percent",
                hovertemplate="<b>%{label}</b><br>$%{value:.2f} (%{percent})<extra></extra>",
                marker=dict(colors=PIE_COLORS, line=dict(color="#0E1117", width=2)),
            ))
            fig.update_layout(**PLOTLY_LAYOUT, height=220, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No allocation data.")
