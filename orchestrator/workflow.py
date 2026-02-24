"""
LangGraph workflow orchestrating the 6-agent trading pipeline.
State flows: initialize → vix_check → macro → scanner → strategy → risk → execution
Optional: → performance → store_memory
"""
import time
from datetime import date as date_type
from typing import TypedDict, Optional, List, Dict
from langgraph.graph import StateGraph, END

from config.logging_config import get_logger
from agents.macro_intelligence import MacroIntelligenceAgent
from agents.market_scanner import MarketScannerAgent
from agents.strategy import StrategyAgent
from agents.risk_allocation import RiskAllocationAgent
from agents.execution_simulation import ExecutionSimulationAgent
from agents.performance_explanation import PerformanceExplanationAgent
from orchestrator.guardrails import VIXGuard, FallbackHandler
from tools.pinecone_memory import retrieve_recent_performance, retrieve_best_performing, store_daily_record
from tools.news_sentiment import get_market_headlines

log = get_logger("workflow")


# ── State ────────────────────────────────────────────────────────────────────

class TradingState(TypedDict):
    date: str
    trading_day_id: Optional[int]
    mode: str                    # "normal" | "defensive"
    vix: Optional[float]
    memory_context: List[Dict]   # last N days from Pinecone
    strategy_perf: List[Dict]    # strategy_performance_summary rows from DB
    best_days: List[Dict]        # best-performing historical days from Pinecone
    market_headlines: List[Dict] # live Polygon.io news headlines

    macro_signals: Dict
    candidate_assets: List[Dict]
    selected_assets: List[Dict]
    allocations: List[Dict]
    asset_metrics_data: Dict     # symbol → {volatility_30d, return_30d}
    executions: List[Dict]
    performance: Dict
    strategy_type: Optional[str] # selected strategy type for memory storage

    errors: List[str]
    run_evaluation: bool


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_strategy_performance() -> List[Dict]:
    """
    Query strategy_performance_summary joined with strategies for all known strategies.
    Returns list of dicts with: strategy_name, cumulative_return, sharpe_ratio, max_drawdown.
    Falls back to [] on any error.
    """
    try:
        from config.database import SessionLocal
        from db.models import Strategy, StrategyPerformanceSummary
        db = SessionLocal()
        try:
            rows = (
                db.query(Strategy, StrategyPerformanceSummary)
                .outerjoin(
                    StrategyPerformanceSummary,
                    Strategy.strategy_id == StrategyPerformanceSummary.strategy_id,
                )
                .all()
            )
            result = []
            for strat, perf in rows:
                result.append({
                    "strategy_name": strat.strategy_name,
                    "cumulative_return": float(perf.cumulative_return) if perf and perf.cumulative_return is not None else 0.0,
                    "sharpe_ratio": float(perf.sharpe_ratio) if perf and perf.sharpe_ratio is not None else 0.0,
                    "max_drawdown": float(perf.max_drawdown) if perf and perf.max_drawdown is not None else 0.0,
                })
            return result
        finally:
            db.close()
    except Exception as e:
        log.warning("[workflow] strategy_performance fetch failed: %s", e)
        return []


# ── Node helpers ─────────────────────────────────────────────────────────────

def _log_decision(state: TradingState, agent_name: str, output: Dict) -> None:
    """Write agent decision to agent_decisions table."""
    trading_day_id = state.get("trading_day_id")
    if not trading_day_id:
        return
    try:
        from config.database import SessionLocal
        from db.models import AgentDecision
        db = SessionLocal()
        try:
            db.add(AgentDecision(
                trading_day_id=trading_day_id,
                agent_name=agent_name,
                decision_json=output,
            ))
            db.commit()
        finally:
            db.close()
    except Exception as e:
        log.warning("[workflow] Decision log failed for %s: %s", agent_name, e)


def _log_violation(trading_day_id: int, violation_type: str, description: str) -> None:
    """Write a risk constraint breach to risk_violations table."""
    if not trading_day_id:
        return
    try:
        from config.database import SessionLocal
        from db.models import RiskViolation
        db = SessionLocal()
        try:
            db.add(RiskViolation(
                trading_day_id=trading_day_id,
                violation_type=violation_type,
                violation_description=description,
            ))
            db.commit()
        finally:
            db.close()
    except Exception as e:
        log.warning("[workflow] Violation log failed: %s", e)


# ── Nodes ─────────────────────────────────────────────────────────────────────

def initialize_session(state: TradingState) -> Dict:
    """Create a trading_days record, retrieve Pinecone memory, and fetch DB strategy performance."""
    today = state.get("date") or str(date_type.today())

    # Fetch recent memory and best-performing days from Pinecone
    memory_context = retrieve_recent_performance(n_days=7)
    best_days = retrieve_best_performing(top_k=5, min_return_pct=0.0)

    # Fetch live market headlines from Polygon.io
    market_headlines = get_market_headlines(limit=15)

    # Fetch historical strategy performance from DB
    strategy_perf = _get_strategy_performance()

    if strategy_perf:
        log.info("[workflow] Strategy perf loaded: %s", [s['strategy_name'] for s in strategy_perf])
    if best_days:
        log.info("[workflow] Best days loaded: top return=%.2f%%", best_days[0].get('portfolio_return', 0))
    if market_headlines:
        log.info("[workflow] %d market headlines fetched from Polygon.io", len(market_headlines))
    else:
        log.warning("[workflow] No market headlines (POLYGON_API_KEY not set or fetch failed)")

    # Create / retrieve DB trading day record
    trading_day_id = None
    try:
        from config.database import SessionLocal
        from db.models import TradingDay
        db = SessionLocal()
        try:
            existing = db.query(TradingDay).filter_by(trade_date=today).first()
            if existing:
                trading_day_id = existing.trading_day_id
            else:
                td = TradingDay(trade_date=today)
                db.add(td)
                db.commit()
                db.refresh(td)
                trading_day_id = td.trading_day_id
        finally:
            db.close()
    except Exception as e:
        log.error("[initialize_session] DB error: %s", e)

    log.info("[workflow] trading_day_id=%s for %s", trading_day_id, today)
    return {
        "date": today,
        "trading_day_id": trading_day_id,
        "memory_context": memory_context,
        "strategy_perf": strategy_perf,
        "best_days": best_days,
        "market_headlines": market_headlines,
    }


def check_vix(state: TradingState) -> Dict:
    """Check VIX and determine trading mode."""
    vix_result = VIXGuard.check()
    log.info("[workflow] VIX check: %s", vix_result)
    return {"vix": vix_result["vix"], "mode": vix_result["mode"]}


def run_macro_agent(state: TradingState) -> Dict:
    """Agent 1: Analyze macro environment using Pinecone memory + DB strategy performance."""
    try:
        agent = MacroIntelligenceAgent()
        result = agent.analyze(
            memory_context=state.get("memory_context", []),
            date=state["date"],
            strategy_perf=state.get("strategy_perf"),
            best_days=state.get("best_days"),
            market_headlines=state.get("market_headlines"),
        )
        _log_decision(state, "macro_intelligence", result)
        log.info("[workflow] Macro: bias=%s, env=%s, confidence=%.2f",
                 result.get('macro_bias'), result.get('risk_environment'), result.get('confidence_score', 0))
        return {"macro_signals": result}
    except Exception as e:
        fb = FallbackHandler.handle(e, "MacroIntelligenceAgent")
        return {
            "errors": state.get("errors", []) + [fb["error"]],
            "macro_signals": {
                "macro_bias": "neutral", "risk_environment": "mixed",
                "dominant_themes": [], "sectors_strength": {}, "confidence_score": 0.5,
            },
        }


def run_scanner_agent(state: TradingState) -> Dict:
    """Agent 2: Scan markets for candidate assets."""
    try:
        agent = MarketScannerAgent()
        result = agent.scan(
            macro_signals=state.get("macro_signals", {}),
            mode=state.get("mode", "normal"),
        )
        candidates = result.get("candidates", [])
        _log_decision(state, "market_scanner", result)
        log.info("[workflow] Scanner: %d candidates found", len(candidates))
        return {"candidate_assets": candidates}
    except Exception as e:
        fb = FallbackHandler.handle(e, "MarketScannerAgent")
        return {"errors": state.get("errors", []) + [fb["error"]], "candidate_assets": []}


def run_strategy_agent(state: TradingState) -> Dict:
    """Agent 3: Select up to 5 assets, biased toward historically profitable strategies."""
    candidates = state.get("candidate_assets", [])
    if not candidates:
        return {"selected_assets": [], "errors": state.get("errors", []) + ["No candidates available"]}
    try:
        agent = StrategyAgent()
        result = agent.select(
            macro_signals=state.get("macro_signals", {}),
            candidates=candidates,
            strategy_perf=state.get("strategy_perf"),
            best_days=state.get("best_days"),
        )
        selected = result.get("selected_assets", [])
        chosen_strategy = result.get("strategy_type")
        _log_decision(state, "strategy", result)
        log.info("[workflow] Strategy: %d assets, type=%s", len(selected), chosen_strategy)

        # Persist macro/strategy metadata to trading_days
        trading_day_id = state.get("trading_day_id")
        if trading_day_id:
            try:
                from config.database import SessionLocal
                from db.models import TradingDay
                db = SessionLocal()
                try:
                    td = db.query(TradingDay).filter_by(trading_day_id=trading_day_id).first()
                    if td:
                        td.macro_bias = state.get("macro_signals", {}).get("macro_bias")
                        td.risk_environment = state.get("macro_signals", {}).get("risk_environment")
                        td.strategy_type = chosen_strategy
                        db.commit()
                finally:
                    db.close()
            except Exception as e:
                log.warning("[workflow] trading_days update error: %s", e)

        return {"selected_assets": selected, "strategy_type": chosen_strategy}
    except Exception as e:
        fb = FallbackHandler.handle(e, "StrategyAgent")
        return {"errors": state.get("errors", []) + [fb["error"]], "selected_assets": []}


def run_risk_agent(state: TradingState) -> Dict:
    """Agent 4: Allocate $100 with validated constraints."""
    selected = state.get("selected_assets", [])
    if not selected:
        return {"allocations": [], "errors": state.get("errors", []) + ["No assets selected"]}
    try:
        agent = RiskAllocationAgent()
        result = agent.allocate(selected_assets=selected)
        allocations = result.get("allocations", [])
        asset_metrics_data = result.get("asset_metrics_data", {})
        _log_decision(state, "risk_allocation", result)
        total = sum(float(a["allocation_dollars"]) for a in allocations)
        log.info("[workflow] Risk: $%.2f across %d assets", total, len(allocations))

        # Log reward:risk violations
        trading_day_id = state.get("trading_day_id")
        for w in result.get("reward_risk_warnings", []):
            if trading_day_id:
                _log_violation(trading_day_id, "low_reward_risk", w["note"])
            log.warning("[workflow] Risk: %s", w["note"])

        return {"allocations": allocations, "asset_metrics_data": asset_metrics_data}
    except Exception as e:
        trading_day_id = state.get("trading_day_id")
        if trading_day_id:
            _log_violation(trading_day_id, "allocation_error", str(e))
        fb = FallbackHandler.handle(e, "RiskAllocationAgent")
        return {"errors": state.get("errors", []) + [fb["error"]], "allocations": []}


def run_execution_agent(state: TradingState) -> Dict:
    """Agent 5: Simulate trades with real yfinance prices."""
    allocations = state.get("allocations", [])
    if not allocations:
        return {"executions": [], "errors": state.get("errors", []) + ["No allocations"]}
    try:
        agent = ExecutionSimulationAgent()
        result = agent.execute(
            allocations=allocations,
            trading_day_id=state.get("trading_day_id"),
            asset_metrics_data=state.get("asset_metrics_data", {}),
        )
        executions = result.get("executions", [])
        _log_decision(state, "execution_simulation", result)
        log.info("[workflow] Execution: %d trades simulated", len(executions))
        return {"executions": executions}
    except Exception as e:
        fb = FallbackHandler.handle(e, "ExecutionSimulationAgent")
        return {"errors": state.get("errors", []) + [fb["error"]], "executions": []}


def run_performance_agent(state: TradingState) -> Dict:
    """Agent 6: Evaluate EOD performance and compare benchmarks."""
    executions = state.get("executions", [])
    if not executions:
        return {"performance": {}, "errors": state.get("errors", []) + ["No executions to evaluate"]}
    try:
        agent = PerformanceExplanationAgent()
        result = agent.evaluate(
            executions=executions,
            trading_day_id=state.get("trading_day_id"),
        )
        _log_decision(state, "performance_explanation", result)
        ret = result.get('portfolio_return', 0)
        sign = "+" if ret >= 0 else ""
        log.info("[workflow] Performance: return=%s%.2f%%, pnl=$%.2f", sign, ret, result.get('pnl', 0))
        return {"performance": result}
    except Exception as e:
        fb = FallbackHandler.handle(e, "PerformanceExplanationAgent")
        return {"errors": state.get("errors", []) + [fb["error"]], "performance": {}}


def store_memory(state: TradingState) -> Dict:
    """Store today's record to Pinecone + agent_memory_log."""
    performance = state.get("performance", {})
    executions = state.get("executions", [])
    lessons = performance.get("lessons", [])

    record = {
        "date": state["date"],
        "macro_bias": state.get("macro_signals", {}).get("macro_bias"),
        "mode": state.get("mode", "normal"),
        "strategy_type": state.get("strategy_type"),  # from strategy agent result
        "symbols": [e.get("symbol") for e in executions],
        "portfolio_return": performance.get("portfolio_return", 0),
        "lessons": lessons,
    }

    # Store in Pinecone
    vector_id = store_daily_record(record, state["date"])
    if vector_id:
        log.info("[workflow] Pinecone memory stored: %s", vector_id)

    # Mirror to agent_memory_log in PostgreSQL
    trading_day_id = state.get("trading_day_id")
    if trading_day_id:
        try:
            from config.database import SessionLocal
            from db.models import AgentMemoryLog
            db = SessionLocal()
            try:
                db.add(AgentMemoryLog(
                    trading_day_id=trading_day_id,
                    lesson_learned="; ".join(lessons) if lessons else None,
                    mistake_identified=None,
                    performance_summary=performance.get("explanation_summary"),
                    embedding_reference_id=vector_id,
                ))
                db.commit()
            finally:
                db.close()
        except Exception as e:
            log.warning("[workflow] agent_memory_log write failed: %s", e)

    return {}


def should_evaluate(state: TradingState) -> str:
    """Conditional edge: only run performance agent if --evaluate flag set."""
    if state.get("run_evaluation") and state.get("executions"):
        return "performance"
    return END


# ── Build Graph ───────────────────────────────────────────────────────────────

def build_workflow() -> StateGraph:
    workflow = StateGraph(TradingState)

    workflow.add_node("initialize", initialize_session)
    workflow.add_node("vix_check", check_vix)
    workflow.add_node("macro", run_macro_agent)
    workflow.add_node("scanner", run_scanner_agent)
    workflow.add_node("strategy", run_strategy_agent)
    workflow.add_node("risk", run_risk_agent)
    workflow.add_node("execution", run_execution_agent)
    workflow.add_node("performance", run_performance_agent)
    workflow.add_node("store_memory", store_memory)

    workflow.set_entry_point("initialize")
    workflow.add_edge("initialize", "vix_check")
    workflow.add_edge("vix_check", "macro")
    workflow.add_edge("macro", "scanner")
    workflow.add_edge("scanner", "strategy")
    workflow.add_edge("strategy", "risk")
    workflow.add_edge("risk", "execution")
    workflow.add_conditional_edges("execution", should_evaluate, {
        "performance": "performance",
        END: END,
    })
    workflow.add_edge("performance", "store_memory")
    workflow.add_edge("store_memory", END)

    return workflow.compile()


def run_daily(run_evaluation: bool = False, target_date: Optional[str] = None) -> Dict:
    """
    Execute the full daily trading workflow.

    Args:
        run_evaluation: If True, also runs EOD performance agent.
        target_date: ISO date string override. Defaults to today.

    Returns:
        Final TradingState dict.
    """
    from config.database import init_db
    init_db()

    app = build_workflow()

    initial_state: TradingState = {
        "date": target_date or str(date_type.today()),
        "trading_day_id": None,
        "mode": "normal",
        "vix": None,
        "memory_context": [],
        "strategy_perf": [],
        "best_days": [],
        "market_headlines": [],
        "macro_signals": {},
        "candidate_assets": [],
        "selected_assets": [],
        "allocations": [],
        "asset_metrics_data": {},
        "executions": [],
        "performance": {},
        "strategy_type": None,
        "errors": [],
        "run_evaluation": run_evaluation,
    }

    return app.invoke(initial_state)
