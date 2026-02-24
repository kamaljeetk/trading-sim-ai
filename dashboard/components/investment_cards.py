"""
Section A: Today's Investment Cards (max 5).
Green border = profit, red border = loss.
Uses st.html() (Streamlit 1.31+) to reliably render card HTML.
"""
import streamlit as st
from dashboard.utils.formatting import fmt_dollars, fmt_pct, pnl_color
from dashboard.utils.theme import CARD_BG, ACCENT, TEXT_MUTED, PROFIT_GREEN, LOSS_RED


def _card_html(pos: dict, current_price, unrealized_pnl, pnl_pct) -> str:
    symbol      = pos["symbol"]
    name        = (pos["name"] or symbol)[:22]
    asset_type  = (pos["asset_type"] or "stock").upper()
    sector      = pos["sector"] or "N/A"
    alloc_d     = pos["allocation_dollars"]
    alloc_pct   = pos["allocation_percentage"]
    conviction  = pos["conviction_score"] or 0.0
    entry       = pos["execution_price"]
    vol         = pos.get("volatility_30d")
    beta        = pos.get("beta_vs_spy")

    border  = PROFIT_GREEN if (unrealized_pnl or 0) >= 0 else LOSS_RED
    pnl_hex = pnl_color(unrealized_pnl)

    entry_str   = fmt_dollars(entry, 4) if entry else "N/A"
    current_str = fmt_dollars(current_price, 4) if current_price else "N/A"

    if unrealized_pnl is not None:
        pnl_str = f"{fmt_dollars(unrealized_pnl)} ({fmt_pct(pnl_pct)})"
    else:
        pnl_str = "N/A"

    vol_str  = f"{vol:.2%}"  if vol  else "N/A"
    beta_str = f"{beta:.2f}" if beta else "N/A"

    return f"""
    <div style="
        background:{CARD_BG};
        border:1px solid {border};
        border-top:3px solid {border};
        border-radius:8px;
        padding:16px 14px;
        font-family:Inter,sans-serif;
        margin-bottom:8px;
    ">
        <div style="font-size:22px;font-weight:700;color:{ACCENT};
                    letter-spacing:1px;">{symbol}</div>
        <div style="font-size:11px;color:{TEXT_MUTED};margin-bottom:4px;">{name}</div>
        <div style="font-size:10px;color:{TEXT_MUTED};margin-bottom:10px;">
            {asset_type} &nbsp;|&nbsp; {sector}
        </div>
        <hr style="border:none;border-top:1px solid {border};opacity:0.25;margin:8px 0;">

        <div style="display:flex;justify-content:space-between;margin:5px 0;font-size:12px;">
            <span style="color:{TEXT_MUTED};">Allocated</span>
            <span style="font-weight:600;">{fmt_dollars(alloc_d)} ({alloc_pct:.1f}%)</span>
        </div>
        <div style="display:flex;justify-content:space-between;margin:5px 0;font-size:12px;">
            <span style="color:{TEXT_MUTED};">Entry</span>
            <span>{entry_str}</span>
        </div>
        <div style="display:flex;justify-content:space-between;margin:5px 0;font-size:12px;">
            <span style="color:{TEXT_MUTED};">Current</span>
            <span>{current_str}</span>
        </div>
        <div style="display:flex;justify-content:space-between;margin:5px 0;font-size:12px;">
            <span style="color:{TEXT_MUTED};">Unrealized P/L</span>
            <span style="color:{pnl_hex};font-weight:700;">{pnl_str}</span>
        </div>
        <div style="display:flex;justify-content:space-between;margin:5px 0;font-size:12px;">
            <span style="color:{TEXT_MUTED};">Conviction</span>
            <span style="color:{ACCENT};font-weight:600;">{conviction:.2f}</span>
        </div>

        <hr style="border:none;border-top:1px solid {border};opacity:0.15;margin:8px 0;">
        <div style="font-size:10px;color:{TEXT_MUTED};">
            Vol: {vol_str} &nbsp;&nbsp; Beta: {beta_str}
        </div>
    </div>
    """


def render_investment_cards(positions: list, live_prices: dict):
    st.markdown("### Today's Portfolio Positions")

    if not positions:
        st.info("No positions for this trading day. Run a simulation first.")
        return

    cols = st.columns(len(positions))

    for col, pos in zip(cols, positions):
        symbol      = pos["symbol"]
        entry_price = pos["execution_price"]
        current     = live_prices.get(symbol)
        shares      = pos["shares"]

        if entry_price and current and shares:
            unrealized_pnl = shares * (current - entry_price)
            pnl_pct        = (current - entry_price) / entry_price * 100
        else:
            unrealized_pnl = None
            pnl_pct        = None

        with col:
            st.html(_card_html(pos, current, unrealized_pnl, pnl_pct))
