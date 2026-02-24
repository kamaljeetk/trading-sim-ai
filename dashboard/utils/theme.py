"""
Centralized color and style constants for Bloomberg-dark aesthetic.
"""

BACKGROUND = "#0E1117"
CARD_BG = "#1A1F2E"
ACCENT = "#00D4AA"
PROFIT_GREEN = "#00C878"
LOSS_RED = "#FF4444"
WARNING_YELLOW = "#FFA500"
TEXT_PRIMARY = "#FAFAFA"
TEXT_MUTED = "#8B9BB4"
GRID_COLOR = "#2A2F3E"
BORDER_COLOR = "#2E3447"

# Plotly dark theme base dict (applied to all charts)
PLOTLY_LAYOUT = dict(
    paper_bgcolor=BACKGROUND,
    plot_bgcolor=CARD_BG,
    font=dict(color=TEXT_PRIMARY, family="Inter, sans-serif", size=12),
    margin=dict(l=40, r=20, t=40, b=40),
)

# Shared axis style — use with fig.update_xaxes(**AXIS_STYLE) / update_yaxes(**AXIS_STYLE)
AXIS_STYLE = dict(
    gridcolor=GRID_COLOR,
    linecolor=BORDER_COLOR,
    tickcolor=TEXT_MUTED,
)

# Default legend style — merge into update_layout as needed
LEGEND_DEFAULT = dict(bgcolor="rgba(0,0,0,0)", bordercolor=BORDER_COLOR)
LEGEND_H = dict(bgcolor="rgba(0,0,0,0)", bordercolor=BORDER_COLOR, orientation="h", y=1.1)

# Traffic-light risk thresholds
RISK_THRESHOLDS = {
    "sharpe":   {"green": 1.0,   "yellow": 0.5},
    "drawdown": {"green": -0.05, "yellow": -0.10},
    "exposure": {"green": 0.4,   "yellow": 0.7},
}

TRAFFIC_COLORS = {
    "green":  PROFIT_GREEN,
    "yellow": WARNING_YELLOW,
    "red":    LOSS_RED,
}

# Card accent colors for pie chart slices (max 5 positions)
PIE_COLORS = [ACCENT, PROFIT_GREEN, "#7B68EE", "#FF6B6B", "#FFD700"]
