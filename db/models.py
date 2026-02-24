"""
SQLAlchemy ORM models matching the new 13-table schema.
"""
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Numeric,
    Boolean, Date, DateTime, ForeignKey, UniqueConstraint, func
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from config.database import Base


# ── 1. Asset Universe ────────────────────────────────────────────────────────

class Asset(Base):
    __tablename__ = "assets"

    asset_id   = Column(Integer, primary_key=True)
    symbol     = Column(String(20), unique=True, nullable=False)
    name       = Column(Text, nullable=False)
    asset_type = Column(String(20), nullable=False)  # stock | etf | bond_etf | index
    sector     = Column(String(100))
    industry   = Column(String(100))
    exchange   = Column(String(50))
    currency   = Column(String(10), default="USD")
    is_active  = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    prices      = relationship("MarketPrice", back_populates="asset")
    metrics     = relationship("AssetMetrics", back_populates="asset")
    allocations = relationship("Allocation", back_populates="asset")


class MarketPrice(Base):
    __tablename__ = "market_prices"
    __table_args__ = (UniqueConstraint("asset_id", "trade_date"),)

    price_id       = Column(BigInteger, primary_key=True)
    asset_id       = Column(Integer, ForeignKey("assets.asset_id"))
    trade_date     = Column(Date, nullable=False)
    open_price     = Column(Numeric(12, 4))
    high_price     = Column(Numeric(12, 4))
    low_price      = Column(Numeric(12, 4))
    close_price    = Column(Numeric(12, 4))
    adjusted_close = Column(Numeric(12, 4))
    volume         = Column(BigInteger)

    asset = relationship("Asset", back_populates="prices")


class AssetMetrics(Base):
    __tablename__ = "asset_metrics"
    __table_args__ = (UniqueConstraint("asset_id", "trade_date"),)

    metric_id      = Column(BigInteger, primary_key=True)
    asset_id       = Column(Integer, ForeignKey("assets.asset_id"))
    trade_date     = Column(Date)
    volatility_30d = Column(Numeric(8, 4))
    return_30d     = Column(Numeric(8, 4))
    beta_vs_spy    = Column(Numeric(8, 4))
    sharpe_ratio   = Column(Numeric(8, 4))

    asset = relationship("Asset", back_populates="metrics")


# ── 2. Portfolio & Simulation Layer ──────────────────────────────────────────

class TradingDay(Base):
    __tablename__ = "trading_days"

    trading_day_id   = Column(Integer, primary_key=True)
    trade_date       = Column(Date, unique=True, nullable=False)
    macro_bias       = Column(String(20))      # bullish | bearish | neutral
    risk_environment = Column(String(20))      # risk_on | risk_off | mixed
    strategy_type    = Column(String(50))      # momentum | defensive | balanced | rotation
    total_capital    = Column(Numeric(10, 2), default=100.00)
    created_at       = Column(DateTime, server_default=func.now())

    allocations   = relationship("Allocation", back_populates="trading_day")
    performance   = relationship("DailyPortfolioPerformance", back_populates="trading_day", uselist=False)
    benchmarks    = relationship("BenchmarkPerformance", back_populates="trading_day")
    decisions     = relationship("AgentDecision", back_populates="trading_day")
    violations    = relationship("RiskViolation", back_populates="trading_day")
    memory_logs   = relationship("AgentMemoryLog", back_populates="trading_day")


class Allocation(Base):
    __tablename__ = "allocations"

    allocation_id         = Column(BigInteger, primary_key=True)
    trading_day_id        = Column(Integer, ForeignKey("trading_days.trading_day_id"))
    asset_id              = Column(Integer, ForeignKey("assets.asset_id"))
    allocation_dollars    = Column(Numeric(10, 2))
    allocation_percentage = Column(Numeric(5, 2))
    conviction_score      = Column(Numeric(4, 2))
    created_at            = Column(DateTime, server_default=func.now())

    trading_day = relationship("TradingDay", back_populates="allocations")
    asset       = relationship("Asset", back_populates="allocations")
    execution   = relationship("Execution", back_populates="allocation", uselist=False)


class Execution(Base):
    __tablename__ = "executions"

    execution_id        = Column(BigInteger, primary_key=True)
    allocation_id       = Column(BigInteger, ForeignKey("allocations.allocation_id"))
    execution_price     = Column(Numeric(12, 4))
    shares              = Column(Numeric(18, 6))
    stop_loss_price     = Column(Numeric(12, 4))   # 6% below entry (swing stop)
    profit_target_price = Column(Numeric(12, 4))   # 12% above entry (2:1 R:R)
    executed_at         = Column(DateTime, server_default=func.now())

    allocation = relationship("Allocation", back_populates="execution")


# ── 3. Performance & Risk ─────────────────────────────────────────────────────

class DailyPortfolioPerformance(Base):
    __tablename__ = "daily_portfolio_performance"

    performance_id      = Column(BigInteger, primary_key=True)
    trading_day_id      = Column(Integer, ForeignKey("trading_days.trading_day_id"))
    portfolio_value     = Column(Numeric(12, 2))
    daily_profit_loss   = Column(Numeric(12, 2))
    daily_return_pct    = Column(Numeric(8, 4))
    sharpe_ratio        = Column(Numeric(8, 4))
    max_drawdown        = Column(Numeric(8, 4))
    risk_exposure_score = Column(Numeric(5, 2))
    created_at          = Column(DateTime, server_default=func.now())

    trading_day = relationship("TradingDay", back_populates="performance")


class BenchmarkPerformance(Base):
    __tablename__ = "benchmark_performance"

    benchmark_id         = Column(BigInteger, primary_key=True)
    trading_day_id       = Column(Integer, ForeignKey("trading_days.trading_day_id"))
    benchmark_symbol     = Column(String(20))
    benchmark_return_pct = Column(Numeric(8, 4))
    benchmark_value      = Column(Numeric(12, 2))
    created_at           = Column(DateTime, server_default=func.now())

    trading_day = relationship("TradingDay", back_populates="benchmarks")


# ── 4. Agent Decision & Audit Layer ──────────────────────────────────────────

class AgentDecision(Base):
    __tablename__ = "agent_decisions"

    decision_id    = Column(BigInteger, primary_key=True)
    trading_day_id = Column(Integer, ForeignKey("trading_days.trading_day_id"))
    agent_name     = Column(String(100))
    decision_json  = Column(JSONB)
    created_at     = Column(DateTime, server_default=func.now())

    trading_day = relationship("TradingDay", back_populates="decisions")


class RiskViolation(Base):
    __tablename__ = "risk_violations"

    violation_id          = Column(BigInteger, primary_key=True)
    trading_day_id        = Column(Integer, ForeignKey("trading_days.trading_day_id"))
    violation_type        = Column(String(100))
    violation_description = Column(Text)
    created_at            = Column(DateTime, server_default=func.now())

    trading_day = relationship("TradingDay", back_populates="violations")


# ── 5. Agent Memory (Pinecone Mirror) ────────────────────────────────────────

class AgentMemoryLog(Base):
    __tablename__ = "agent_memory_log"

    memory_id              = Column(BigInteger, primary_key=True)
    trading_day_id         = Column(Integer, ForeignKey("trading_days.trading_day_id"))
    lesson_learned         = Column(Text)
    mistake_identified     = Column(Text)
    performance_summary    = Column(Text)
    embedding_reference_id = Column(String(100))
    created_at             = Column(DateTime, server_default=func.now())

    trading_day = relationship("TradingDay", back_populates="memory_logs")


# ── 6. Strategy Framework ─────────────────────────────────────────────────────

class Strategy(Base):
    __tablename__ = "strategies"

    strategy_id   = Column(Integer, primary_key=True)
    strategy_name = Column(String(100), unique=True)
    description   = Column(Text)
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, server_default=func.now())

    performance_summaries = relationship("StrategyPerformanceSummary", back_populates="strategy")


class StrategyPerformanceSummary(Base):
    __tablename__ = "strategy_performance_summary"

    summary_id           = Column(BigInteger, primary_key=True)
    strategy_id          = Column(Integer, ForeignKey("strategies.strategy_id"))
    cumulative_return    = Column(Numeric(10, 4))
    average_daily_return = Column(Numeric(8, 4))
    volatility           = Column(Numeric(8, 4))
    sharpe_ratio         = Column(Numeric(8, 4))
    max_drawdown         = Column(Numeric(8, 4))
    last_updated         = Column(DateTime, server_default=func.now(), onupdate=func.now())

    strategy = relationship("Strategy", back_populates="performance_summaries")
