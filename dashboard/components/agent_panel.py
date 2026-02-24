"""
Section F: Agent Explanation Panel.
Macro reasoning, strategy rationale, memory references, risk violations.
"""
from typing import Optional
import streamlit as st
from dashboard.utils.theme import ACCENT, LOSS_RED, TEXT_MUTED


def render_agent_panel(decisions: list, violations: list, memory_log: Optional[dict]):
    st.markdown("### Agent Intelligence Summary")

    decision_map = {d["agent_name"]: d for d in decisions}

    # ── Macro Agent ────────────────────────────────────────────────────────────
    macro = decision_map.get("macro_intelligence")
    if macro:
        data = macro.get("decision_json") or {}
        with st.expander("Macro Intelligence Agent", expanded=True):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Bias:** `{data.get('macro_bias', 'N/A')}`")
                st.markdown(f"**Risk Env:** `{data.get('risk_environment', 'N/A')}`")
                st.markdown(f"**Confidence:** `{data.get('confidence_score', 0):.2f}`")
            with c2:
                for theme in data.get("dominant_themes", []):
                    st.markdown(f"- {theme}")

            sectors = data.get("sectors_strength", {})
            if sectors:
                st.markdown("**Sector Strengths:**")
                color_map = {"strong": ACCENT, "neutral": TEXT_MUTED, "weak": LOSS_RED}
                for sector, strength in sectors.items():
                    c = color_map.get(strength, TEXT_MUTED)
                    st.html(f'<span style="color:{c};">● {sector}: {strength}</span>')
    else:
        st.caption("Macro agent data not available for this day.")

    # ── Strategy Agent ─────────────────────────────────────────────────────────
    strategy = decision_map.get("strategy")
    if strategy:
        data = strategy.get("decision_json") or {}
        with st.expander("Strategy Agent — Asset Selection Rationale", expanded=True):
            st.markdown(
                f"**Strategy:** `{data.get('strategy_type', 'N/A')}`  "
                f"**Diversification:** `{data.get('diversification_score', 0):.2f}`"
            )
            for asset in data.get("selected_assets", []):
                st.markdown(
                    f"**{asset.get('symbol')}** "
                    f"(conviction: {float(asset.get('conviction_score', 0)):.2f}): "
                    f"{asset.get('strategic_reason', 'N/A')}"
                )

    # ── Memory Log ─────────────────────────────────────────────────────────────
    if memory_log:
        with st.expander("Agent Memory References", expanded=False):
            lesson = memory_log.get("lesson_learned") or ""
            if lesson:
                st.markdown("**Lessons Learned:**")
                for l in lesson.split("; "):
                    if l.strip():
                        st.markdown(f"- {l.strip()}")
            summary = memory_log.get("performance_summary")
            if summary:
                st.caption(summary)

    # ── Risk Violations ────────────────────────────────────────────────────────
    if violations:
        with st.expander(f"Risk Violations ({len(violations)})", expanded=True):
            for v in violations:
                st.error(
                    f"**{v['violation_type'].replace('_', ' ').title()}**: {v['description']}"
                )
    else:
        st.success("No risk violations for this session.")
