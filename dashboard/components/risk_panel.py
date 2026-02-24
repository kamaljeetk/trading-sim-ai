"""
Section E: Risk Panel.
Traffic-light badges for Sharpe / Drawdown / Exposure + gauge chart.
Diversification score from unique sectors.
"""
from typing import Optional
import streamlit as st
import plotly.graph_objects as go
from dashboard.utils.theme import (
    PLOTLY_LAYOUT, AXIS_STYLE, CARD_BG, TRAFFIC_COLORS, RISK_THRESHOLDS, TEXT_MUTED, ACCENT
)
from dashboard.utils.formatting import fmt_pct


def _traffic(metric: str, value: float) -> str:
    t = RISK_THRESHOLDS.get(metric, {})
    g, y = t.get("green", 1), t.get("yellow", 0)
    if metric == "sharpe":
        return "green" if value >= g else ("yellow" if value >= y else "red")
    elif metric == "drawdown":
        return "green" if value >= g else ("yellow" if value >= y else "red")
    elif metric == "exposure":
        return "green" if value <= g else ("yellow" if value <= y else "red")
    return "yellow"


def _badge_html(label: str, value_str: str, status: str) -> str:
    c = TRAFFIC_COLORS[status]
    return f"""
    <div style="background:{CARD_BG};border:1px solid {c};border-left:4px solid {c};
                border-radius:6px;padding:12px 14px;margin:6px 0;">
        <div style="font-size:10px;color:{TEXT_MUTED};text-transform:uppercase;
                    letter-spacing:0.5px;">{label}</div>
        <div style="font-size:20px;font-weight:700;color:{c};margin-top:2px;">
            {value_str}
        </div>
    </div>"""


def render_risk_panel(performance: Optional[dict], positions: list):
    st.markdown("### Risk Dashboard")

    if not performance:
        st.info("Risk metrics available after running --evaluate.")
        return

    sharpe   = performance.get("sharpe_ratio", 0)
    drawdown = performance.get("max_drawdown", 0)
    exposure = performance.get("risk_exposure_score", 0)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.html(_badge_html("Sharpe Ratio", f"{sharpe:.4f}", _traffic("sharpe", sharpe)))
    with c2:
        st.html(_badge_html("Max Drawdown", fmt_pct(drawdown * 100), _traffic("drawdown", drawdown)))
    with c3:
        st.html(_badge_html("Risk Exposure", f"{exposure:.2f}", _traffic("exposure", exposure)))

    # Diversification score
    if positions:
        sectors = [p["sector"] for p in positions if p.get("sector") and p["sector"] != "N/A"]
        unique = len(set(sectors))
        n = len(positions)
        score = min(unique / max(n, 1), 1.0)
        status = "green" if score >= 0.6 else ("yellow" if score >= 0.4 else "red")
        st.html(_badge_html(
            "Diversification Score",
            f"{score:.2f}  ({unique} sectors, {n} positions)",
            status,
        ))

    # Gauge chart
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=float(exposure),
        title=dict(text="Risk Exposure Score", font=dict(color="#FAFAFA", size=13)),
        number=dict(font=dict(color="#FAFAFA", size=26)),
        gauge=dict(
            axis=dict(range=[0, 1], tickcolor="#FAFAFA"),
            bar=dict(color=ACCENT),
            bgcolor=CARD_BG,
            bordercolor="rgba(0,0,0,0)",
            steps=[
                dict(range=[0,   0.4], color="rgba(0,200,120,0.12)"),
                dict(range=[0.4, 0.7], color="rgba(255,165,0,0.12)"),
                dict(range=[0.7, 1.0], color="rgba(255,68,68,0.12)"),
            ],
            threshold=dict(line=dict(color="#FF4444", width=3), thickness=0.8, value=0.7),
        ),
    ))
    fig.update_layout(**PLOTLY_LAYOUT, height=230)
    fig.update_xaxes(**AXIS_STYLE)
    fig.update_yaxes(**AXIS_STYLE)
    st.plotly_chart(fig, use_container_width=True)
