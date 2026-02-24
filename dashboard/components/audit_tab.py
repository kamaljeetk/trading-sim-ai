"""
Section H: Agent Audit Trail.
Per-agent JSON accordion, allocation validation, risk violations log.
"""
import json
import streamlit as st
from dashboard.utils.theme import CARD_BG, ACCENT, LOSS_RED, TEXT_MUTED


AGENT_ORDER = [
    "macro_intelligence",
    "market_scanner",
    "strategy",
    "risk_allocation",
    "execution_simulation",
    "performance_explanation",
]

AGENT_LABELS = {
    "macro_intelligence":      "Agent 1 — Macro Intelligence",
    "market_scanner":          "Agent 2 — Market Scanner",
    "strategy":                "Agent 3 — Strategy",
    "risk_allocation":         "Agent 4 — Risk & Allocation",
    "execution_simulation":    "Agent 5 — Execution Simulation",
    "performance_explanation":  "Agent 6 — Performance Explanation",
}


def _check(label: str, passed: bool):
    color = "#00C878" if passed else "#FF4444"
    mark  = "PASS" if passed else "FAIL"
    st.html(f'<span style="color:{color};font-weight:600;">[{mark}]</span> {label}')


def render_audit_tab(decisions: list, violations: list):
    st.markdown("### Agent Audit Trail")

    if not decisions:
        st.info("No agent decisions recorded. Run a simulation first.")
        return

    decision_map = {d["agent_name"]: d for d in decisions}

    # ── Per-Agent Accordions ───────────────────────────────────────────────────
    for name in AGENT_ORDER:
        if name not in decision_map:
            continue
        decision = decision_map[name]
        payload  = decision.get("decision_json") or {}
        ts       = decision.get("created_at", "")[:19]

        with st.expander(f"{AGENT_LABELS.get(name, name)}  ·  {ts}", expanded=False):
            col_json, col_summary = st.columns([1, 1])

            with col_json:
                st.markdown("**Raw JSON:**")
                st.code(json.dumps(payload, indent=2, default=str), language="json")

            with col_summary:
                st.markdown("**Key Outputs:**")

                if name == "macro_intelligence":
                    st.write(f"Bias: `{payload.get('macro_bias')}`")
                    st.write(f"Risk Env: `{payload.get('risk_environment')}`")
                    st.write(f"Confidence: `{payload.get('confidence_score', 0):.2f}`")
                    dur = payload.get("_duration_ms")
                    if dur:
                        st.write(f"Duration: `{dur}ms`")

                elif name == "market_scanner":
                    candidates = payload.get("candidate_assets", [])
                    st.write(f"Candidates found: **{len(candidates)}**")
                    for c in candidates:
                        st.caption(
                            f"- {c.get('symbol')}: "
                            f"{str(c.get('reason_for_selection', ''))[:60]}"
                        )

                elif name == "strategy":
                    selected = payload.get("selected_assets", [])
                    st.write(f"Assets selected: **{len(selected)}**")
                    st.write(f"Strategy: `{payload.get('strategy_type')}`")
                    st.write(f"Diversification: `{payload.get('diversification_score', 0):.2f}`")
                    for a in selected:
                        st.caption(
                            f"- {a.get('symbol')} "
                            f"(conviction: {float(a.get('conviction_score', 0)):.2f})"
                        )

                elif name == "risk_allocation":
                    allocs = payload.get("allocations", [])
                    total  = sum(float(a.get("allocation_dollars", 0)) for a in allocs)
                    st.write(f"Total allocated: `${total:.2f}`")
                    st.write(f"Risk Exposure: `{payload.get('risk_exposure_score', 0):.2f}`")
                    ok = abs(total - 100) < 0.01
                    c = "#00C878" if ok else "#FF4444"
                    st.html(f'<span style="color:{c};font-weight:700;">Validation: {"PASS" if ok else "FAIL"}</span>')

                elif name == "execution_simulation":
                    execs = payload.get("executions", [])
                    st.write(f"Trades executed: **{len(execs)}**")
                    st.write(f"Total invested: `${payload.get('total_invested', 0):.2f}`")
                    for e in execs:
                        st.caption(
                            f"- {e.get('symbol')}: "
                            f"{float(e.get('shares', 0)):.6f} shares "
                            f"@ ${float(e.get('price', 0)):.4f}"
                        )

                elif name == "performance_explanation":
                    st.write(f"Portfolio Return: `{payload.get('portfolio_return', 0):.4f}%`")
                    st.write(f"P&L: `${payload.get('pnl', 0):.2f}`")
                    st.write(f"Total Value: `${payload.get('total_value', 0):.2f}`")
                    lessons = payload.get("lessons", [])
                    if lessons:
                        st.markdown("**Lessons:**")
                        for lesson in lessons:
                            st.caption(f"- {lesson}")

    # ── Allocation Validation ──────────────────────────────────────────────────
    st.divider()
    st.markdown("#### Allocation Constraint Validation")
    risk = decision_map.get("risk_allocation", {})
    if risk:
        allocs = (risk.get("decision_json") or {}).get("allocations", [])
        if allocs:
            total  = sum(float(a.get("allocation_dollars", 0)) for a in allocs)
            values = [float(a.get("allocation_dollars", 0)) for a in allocs]
            _check("Total == $100",       abs(total - 100) < 0.01)
            _check("Max 5 assets",        len(allocs) <= 5)
            _check("All allocations ≥ $10", all(v >= 10 for v in values))
            _check("No negative values",  all(v >= 0  for v in values))
        else:
            st.caption("No allocation data found in agent output.")

    # ── Risk Violations Log ────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### Risk Violations Log")
    if violations:
        for v in violations:
            st.error(
                f"**{v['violation_type']}** ({v['created_at'][:19]}): {v['description']}"
            )
    else:
        st.success("No risk violations for this session.")
