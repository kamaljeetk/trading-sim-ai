"""
AI Agentic Trading Simulation Dashboard
Bloomberg-style dark-mode Streamlit UI.

Run:
    streamlit run dashboard.py
"""
import sys
import subprocess
from datetime import date

import streamlit as st

# ── Page config MUST be the first Streamlit call ──────────────────────────────
st.set_page_config(
    page_title="AI Trading Sim",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer    {visibility: hidden;}
    header    {visibility: hidden;}
    [data-testid="collapsedControl"] {
        visibility: visible !important;
        display: block !important;
    }
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        padding-left: 1.5rem;
        padding-right: 1.5rem;
    }
    ::-webkit-scrollbar        { width: 6px; }
    ::-webkit-scrollbar-track  { background: #0E1117; }
    ::-webkit-scrollbar-thumb  { background: #2E3447; border-radius: 3px; }
</style>
""", unsafe_allow_html=True)

# ── Project root (needed for subprocess cwd) ──────────────────────────────────
import os
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ── Lazy imports (after page config) ─────────────────────────────────────────
from config.database import init_db
from dashboard.data import queries
from dashboard.data import live_prices as lp
from dashboard.components.investment_cards  import render_investment_cards
from dashboard.components.daily_summary     import render_daily_summary
from dashboard.components.benchmark_panel   import render_benchmark_comparison
from dashboard.components.performance_charts import render_performance_charts
from dashboard.components.risk_panel        import render_risk_panel
from dashboard.components.agent_panel       import render_agent_panel
from dashboard.components.historical_tab    import render_historical_tab
from dashboard.components.audit_tab         import render_audit_tab


# ── DB init (once per process) ────────────────────────────────────────────────
@st.cache_resource
def _init_db():
    try:
        init_db()
    except Exception as e:
        st.error(f"Database connection failed: {e}")

_init_db()


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────

def _run_subprocess(args: list, label: str):
    """Stream main.py output live into a st.status() panel."""
    import time

    # Keywords that map to agent progress labels
    AGENT_LABELS = {
        "[VIXGuard]":        "VIX Guard — checking market risk mode",
        "[workflow] VIX":    "VIX check complete",
        "[workflow] Macro":  "Agent 1 — Macro Intelligence",
        "[workflow] Scanner":"Agent 2 — Market Scanner",
        "[workflow] Strategy":"Agent 3 — Strategy",
        "[workflow] Risk":   "Agent 4 — Risk & Allocation",
        "[workflow] Execution":"Agent 5 — Execution Simulation",
        "[workflow] Performance":"Agent 6 — Performance Evaluation",
        "[evaluate_only]":   "EOD — loading existing session",
        "[PineconeMemory]":  "Pinecone memory",
        "[NewsSentiment]":   "News sentiment fetch",
        "[FallbackHandler]": "⚠️ Agent fallback triggered",
        "SUMMARY":           "Pipeline complete — writing summary",
    }

    with st.status(f"Running: {label}", expanded=True) as status:
        log_lines = []
        stderr_lines = []

        try:
            proc = subprocess.Popen(
                [sys.executable, "-u", "main.py"] + args,  # -u = unbuffered stdout
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=PROJECT_ROOT,
            )

            log_area = st.empty()

            import threading

            def read_stderr():
                for line in proc.stderr:
                    line = line.rstrip()
                    if line:
                        stderr_lines.append(line)

            stderr_thread = threading.Thread(target=read_stderr, daemon=True)
            stderr_thread.start()

            deadline = time.time() + 360

            for line in proc.stdout:
                if time.time() > deadline:
                    proc.kill()
                    status.update(label="Timed out after 6 minutes", state="error")
                    return

                line = line.rstrip()
                if not line:
                    continue

                # Resolve a human-readable label for known keywords
                display = line
                for keyword, friendly in AGENT_LABELS.items():
                    if keyword in line:
                        display = f"**{friendly}**  \n`{line}`"
                        status.update(label=friendly)
                        break

                log_lines.append(display)
                # Show last 20 lines to avoid overflow
                log_area.markdown("\n\n".join(log_lines[-20:]))

            proc.wait()
            stderr_thread.join(timeout=2)

            if proc.returncode == 0:
                status.update(label=f"{label} complete!", state="complete", expanded=False)
                st.cache_data.clear()
                st.rerun()
            else:
                err = "\n".join(stderr_lines[-20:]) if stderr_lines else "(no stderr)"
                status.update(label=f"{label} failed", state="error", expanded=True)
                st.error(f"```\n{err}\n```")

        except Exception as e:
            status.update(label=f"Failed to start: {e}", state="error")
            st.error(str(e))


with st.sidebar:
    st.markdown("## 📈 AI Trading Sim")
    st.divider()

    # ── Simulation Controls ────────────────────────────────────────────────────
    st.markdown("### Simulation Controls")

    col_run, col_eval = st.columns(2)
    with col_run:
        if st.button("▶ Run Daily", use_container_width=True, type="primary"):
            with st.spinner("Running morning allocation (60-90s)..."):
                _run_subprocess(["--run-daily"], "Morning allocation")

    with col_eval:
        if st.button("⚡ Full Day", use_container_width=True):
            with st.spinner("Running full day simulation..."):
                _run_subprocess(["--run-daily", "--evaluate"], "Full day simulation")

    if st.button("📊 EOD Evaluate", use_container_width=True):
        with st.spinner("Running EOD evaluation on today's session..."):
            _run_subprocess(["--evaluate-only"], "EOD evaluation")

    st.divider()

    # ── Date Selector ──────────────────────────────────────────────────────────
    st.markdown("### View Trading Day")
    all_dates = queries.get_all_trading_dates()

    if all_dates:
        selected_date = st.selectbox(
            "Select date:",
            options=all_dates,
            index=0,
            label_visibility="collapsed",
        )
    else:
        selected_date = None
        st.caption("No simulations run yet.")

    st.divider()

    # ── Backtest ───────────────────────────────────────────────────────────────
    st.markdown("### Backtest")
    backtest_date = st.date_input(
        "Date:",
        value=date.today(),
        min_value=date(2020, 1, 1),
        max_value=date.today(),
        label_visibility="collapsed",
    )
    if st.button("Run Backtest", use_container_width=True):
        with st.spinner(f"Backtesting {backtest_date}..."):
            _run_subprocess(
                ["--run-daily", "--evaluate", "--date", str(backtest_date)],
                f"Backtest {backtest_date}",
            )

    st.divider()
    st.caption("Prices refresh every 30s · DB every 60s")
    if st.button("🔄 Force Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADING
# ─────────────────────────────────────────────────────────────────────────────

# Determine active trading day
if selected_date:
    trading_day = queries.get_trading_day_by_date(selected_date)
else:
    trading_day = queries.get_latest_trading_day()

trading_day_id = trading_day["trading_day_id"] if trading_day else None

# Load all data for the selected day
positions    = queries.get_positions_for_day(trading_day_id)    if trading_day_id else []
performance  = queries.get_performance_for_day(trading_day_id)  if trading_day_id else None
benchmarks   = queries.get_benchmarks_for_day(trading_day_id)   if trading_day_id else []
decisions    = queries.get_agent_decisions_for_day(trading_day_id) if trading_day_id else []
violations   = queries.get_risk_violations_for_day(trading_day_id) if trading_day_id else []
memory_log   = queries.get_memory_log_for_day(trading_day_id)   if trading_day_id else None

# Global historical data (used in multiple tabs)
perf_history      = queries.get_all_performance_history()
strategy_summary  = queries.get_strategy_performance_summary()
historical_stats  = queries.get_historical_stats()

# Live prices (batch fetched once, shared across all components)
if positions:
    live_prices_data = lp.fetch_live_prices(tuple(p["symbol"] for p in positions))
else:
    live_prices_data = {}

spy_history = lp.fetch_spy_history_30d()


# ─────────────────────────────────────────────────────────────────────────────
# TAB LAYOUT
# ─────────────────────────────────────────────────────────────────────────────

tab_today, tab_history, tab_audit = st.tabs([
    "📊 Today's Session",
    "📈 Historical Performance",
    "🔍 Agent Audit Trail",
])


# ── Tab 1: Today ──────────────────────────────────────────────────────────────
with tab_today:
    # B: Daily Summary Header
    render_daily_summary(trading_day, performance)

    st.divider()

    # A: Investment Cards
    render_investment_cards(positions, live_prices_data)

    st.divider()

    # C + D: Benchmarks | Performance Charts
    col_bench, col_charts = st.columns([2, 3])
    with col_bench:
        st.markdown("### Benchmark Comparison")
        portfolio_return = performance.get("daily_return_pct", 0) if performance else 0.0
        render_benchmark_comparison(portfolio_return, benchmarks, perf_history, spy_history)

    with col_charts:
        st.markdown("### Performance Charts")
        render_performance_charts(perf_history, positions)

    st.divider()

    # E + F: Risk Panel | Agent Explanation
    col_risk, col_agent = st.columns([1, 2])
    with col_risk:
        render_risk_panel(performance, positions)

    with col_agent:
        render_agent_panel(decisions, violations, memory_log)


# ── Tab 2: Historical ─────────────────────────────────────────────────────────
with tab_history:
    render_historical_tab(perf_history, strategy_summary, historical_stats)


# ── Tab 3: Audit ──────────────────────────────────────────────────────────────
with tab_audit:
    render_audit_tab(decisions, violations)
