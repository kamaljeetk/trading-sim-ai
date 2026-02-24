"""
All database query functions for the dashboard.
All functions return plain dicts (required for Streamlit cache serialization).
All functions are cached with @st.cache_data(ttl=60).
"""
from typing import Optional
import streamlit as st
from sqlalchemy import desc
from config.database import SessionLocal
from db.models import (
    TradingDay, Allocation, Execution, Asset, AssetMetrics,
    DailyPortfolioPerformance, BenchmarkPerformance,
    AgentDecision, RiskViolation, AgentMemoryLog,
    Strategy, StrategyPerformanceSummary,
)


def _db():
    return SessionLocal()


# ─── Trading Day ───────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def get_latest_trading_day() -> Optional[dict]:
    db = _db()
    try:
        td = db.query(TradingDay).order_by(desc(TradingDay.trade_date)).first()
        if not td:
            return None
        return {
            "trading_day_id": td.trading_day_id,
            "trade_date": str(td.trade_date),
            "macro_bias": td.macro_bias,
            "risk_environment": td.risk_environment,
            "strategy_type": td.strategy_type,
            "total_capital": float(td.total_capital or 100),
        }
    finally:
        db.close()


@st.cache_data(ttl=60)
def get_trading_day_by_date(trade_date: str) -> Optional[dict]:
    db = _db()
    try:
        td = db.query(TradingDay).filter(TradingDay.trade_date == trade_date).first()
        if not td:
            return None
        return {
            "trading_day_id": td.trading_day_id,
            "trade_date": str(td.trade_date),
            "macro_bias": td.macro_bias,
            "risk_environment": td.risk_environment,
            "strategy_type": td.strategy_type,
            "total_capital": float(td.total_capital or 100),
        }
    finally:
        db.close()


@st.cache_data(ttl=60)
def get_all_trading_dates() -> list:
    db = _db()
    try:
        rows = (
            db.query(TradingDay.trade_date)
            .order_by(desc(TradingDay.trade_date))
            .all()
        )
        return [str(r.trade_date) for r in rows]
    finally:
        db.close()


# ─── Positions (Section A) ────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def get_positions_for_day(trading_day_id: int) -> list:
    db = _db()
    try:
        td = db.query(TradingDay).filter_by(trading_day_id=trading_day_id).first()
        trade_date = td.trade_date if td else None

        rows = (
            db.query(Allocation, Asset, Execution, AssetMetrics)
            .join(Asset, Allocation.asset_id == Asset.asset_id)
            .outerjoin(Execution, Execution.allocation_id == Allocation.allocation_id)
            .outerjoin(
                AssetMetrics,
                (AssetMetrics.asset_id == Asset.asset_id) &
                (AssetMetrics.trade_date == trade_date),
            )
            .filter(Allocation.trading_day_id == trading_day_id)
            .all()
        )

        result = []
        for alloc, asset, exe, metrics in rows:
            result.append({
                "symbol": asset.symbol,
                "name": asset.name or asset.symbol,
                "asset_type": asset.asset_type or "stock",
                "sector": asset.sector or "N/A",
                "allocation_dollars": float(alloc.allocation_dollars or 0),
                "allocation_percentage": float(alloc.allocation_percentage or 0),
                "conviction_score": float(alloc.conviction_score or 0),
                "execution_price": float(exe.execution_price) if exe else None,
                "shares": float(exe.shares) if exe else None,
                "executed_at": str(exe.executed_at) if exe else None,
                "volatility_30d": float(metrics.volatility_30d) if metrics and metrics.volatility_30d else None,
                "beta_vs_spy": float(metrics.beta_vs_spy) if metrics and metrics.beta_vs_spy else None,
            })
        # Sort by allocation descending
        return sorted(result, key=lambda x: x["allocation_dollars"], reverse=True)
    finally:
        db.close()


# ─── Performance (Sections B, D, E) ──────────────────────────────────────────

@st.cache_data(ttl=60)
def get_performance_for_day(trading_day_id: int) -> Optional[dict]:
    db = _db()
    try:
        perf = db.query(DailyPortfolioPerformance).filter_by(
            trading_day_id=trading_day_id
        ).first()
        if not perf:
            return None
        return {
            "portfolio_value": float(perf.portfolio_value or 0),
            "daily_profit_loss": float(perf.daily_profit_loss or 0),
            "daily_return_pct": float(perf.daily_return_pct or 0),
            "sharpe_ratio": float(perf.sharpe_ratio or 0),
            "max_drawdown": float(perf.max_drawdown or 0),
            "risk_exposure_score": float(perf.risk_exposure_score or 0),
        }
    finally:
        db.close()


@st.cache_data(ttl=60)
def get_all_performance_history() -> list:
    db = _db()
    try:
        rows = (
            db.query(TradingDay, DailyPortfolioPerformance)
            .join(
                DailyPortfolioPerformance,
                DailyPortfolioPerformance.trading_day_id == TradingDay.trading_day_id,
            )
            .order_by(TradingDay.trade_date.asc())
            .all()
        )
        result = []
        for td, perf in rows:
            result.append({
                "trade_date": str(td.trade_date),
                "strategy_type": td.strategy_type or "N/A",
                "macro_bias": td.macro_bias or "N/A",
                "portfolio_value": float(perf.portfolio_value or 0),
                "daily_return_pct": float(perf.daily_return_pct or 0),
                "daily_profit_loss": float(perf.daily_profit_loss or 0),
                "sharpe_ratio": float(perf.sharpe_ratio or 0),
                "max_drawdown": float(perf.max_drawdown or 0),
                "risk_exposure_score": float(perf.risk_exposure_score or 0),
            })
        return result
    finally:
        db.close()


# ─── Benchmarks (Section C) ───────────────────────────────────────────────────

@st.cache_data(ttl=60)
def get_benchmarks_for_day(trading_day_id: int) -> list:
    db = _db()
    try:
        rows = db.query(BenchmarkPerformance).filter_by(
            trading_day_id=trading_day_id
        ).all()
        return [
            {
                "symbol": r.benchmark_symbol,
                "return_pct": float(r.benchmark_return_pct or 0),
                "value": float(r.benchmark_value or 0),
            }
            for r in rows
        ]
    finally:
        db.close()


@st.cache_data(ttl=60)
def get_benchmark_history_30d(benchmark_symbol: str = "SPY") -> list:
    db = _db()
    try:
        rows = (
            db.query(TradingDay.trade_date, BenchmarkPerformance.benchmark_return_pct)
            .join(
                BenchmarkPerformance,
                BenchmarkPerformance.trading_day_id == TradingDay.trading_day_id,
            )
            .filter(BenchmarkPerformance.benchmark_symbol == benchmark_symbol)
            .order_by(TradingDay.trade_date.desc())
            .limit(30)
            .all()
        )
        return [
            {"trade_date": str(r.trade_date), "return_pct": float(r.benchmark_return_pct or 0)}
            for r in reversed(rows)
        ]
    finally:
        db.close()


# ─── Agent Decisions (Sections F, H) ─────────────────────────────────────────

@st.cache_data(ttl=60)
def get_agent_decisions_for_day(trading_day_id: int) -> list:
    db = _db()
    try:
        rows = (
            db.query(AgentDecision)
            .filter_by(trading_day_id=trading_day_id)
            .order_by(AgentDecision.created_at.asc())
            .all()
        )
        return [
            {
                "agent_name": r.agent_name,
                "decision_json": r.decision_json or {},
                "created_at": str(r.created_at),
            }
            for r in rows
        ]
    finally:
        db.close()


@st.cache_data(ttl=60)
def get_risk_violations_for_day(trading_day_id: int) -> list:
    db = _db()
    try:
        rows = db.query(RiskViolation).filter_by(trading_day_id=trading_day_id).all()
        return [
            {
                "violation_type": r.violation_type,
                "description": r.violation_description,
                "created_at": str(r.created_at),
            }
            for r in rows
        ]
    finally:
        db.close()


@st.cache_data(ttl=60)
def get_memory_log_for_day(trading_day_id: int) -> Optional[dict]:
    db = _db()
    try:
        row = db.query(AgentMemoryLog).filter_by(trading_day_id=trading_day_id).first()
        if not row:
            return None
        return {
            "lesson_learned": row.lesson_learned,
            "mistake_identified": row.mistake_identified,
            "performance_summary": row.performance_summary,
            "embedding_reference_id": row.embedding_reference_id,
        }
    finally:
        db.close()


# ─── Strategy Performance (Section G) ────────────────────────────────────────

@st.cache_data(ttl=60)
def get_strategy_performance_summary() -> list:
    db = _db()
    try:
        rows = (
            db.query(Strategy, StrategyPerformanceSummary)
            .outerjoin(
                StrategyPerformanceSummary,
                Strategy.strategy_id == StrategyPerformanceSummary.strategy_id,
            )
            .filter(Strategy.is_active == True)
            .all()
        )
        result = []
        for s, perf in rows:
            result.append({
                "strategy_name": s.strategy_name,
                "cumulative_return": float(perf.cumulative_return or 0) if perf else 0.0,
                "avg_daily_return": float(perf.average_daily_return or 0) if perf else 0.0,
                "sharpe_ratio": float(perf.sharpe_ratio or 0) if perf else 0.0,
                "max_drawdown": float(perf.max_drawdown or 0) if perf else 0.0,
                "volatility": float(perf.volatility or 0) if perf else 0.0,
            })
        return sorted(result, key=lambda x: x["cumulative_return"], reverse=True)
    finally:
        db.close()


@st.cache_data(ttl=60)
def get_historical_stats() -> dict:
    db = _db()
    try:
        rows = db.query(DailyPortfolioPerformance).all()
        if not rows:
            return {
                "total_days": 0, "win_rate": 0,
                "avg_daily_return": 0, "best_day": 0, "worst_day": 0,
            }
        returns = [float(r.daily_return_pct or 0) for r in rows]
        wins = sum(1 for r in returns if r > 0)
        return {
            "total_days": len(returns),
            "win_rate": round(wins / len(returns) * 100, 1),
            "avg_daily_return": round(sum(returns) / len(returns), 4),
            "best_day": round(max(returns), 4),
            "worst_day": round(min(returns), 4),
        }
    finally:
        db.close()
