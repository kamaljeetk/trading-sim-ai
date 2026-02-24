-- ============================================================
-- Agentic Trading Simulation System - PostgreSQL Schema
-- Run: psql trading_sim < db/schema.sql
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- 1. ASSET UNIVERSE
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS assets (
    asset_id   SERIAL PRIMARY KEY,
    symbol     VARCHAR(20) UNIQUE NOT NULL,
    name       TEXT NOT NULL,
    asset_type VARCHAR(20) CHECK (
        asset_type IN ('stock', 'etf', 'bond_etf', 'index')
    ) NOT NULL,
    sector     VARCHAR(100),
    industry   VARCHAR(100),
    exchange   VARCHAR(50),
    currency   VARCHAR(10) DEFAULT 'USD',
    is_active  BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS market_prices (
    price_id       BIGSERIAL PRIMARY KEY,
    asset_id       INT REFERENCES assets(asset_id),
    trade_date     DATE NOT NULL,
    open_price     NUMERIC(12,4),
    high_price     NUMERIC(12,4),
    low_price      NUMERIC(12,4),
    close_price    NUMERIC(12,4),
    adjusted_close NUMERIC(12,4),
    volume         BIGINT,
    UNIQUE(asset_id, trade_date)
);

CREATE TABLE IF NOT EXISTS asset_metrics (
    metric_id      BIGSERIAL PRIMARY KEY,
    asset_id       INT REFERENCES assets(asset_id),
    trade_date     DATE,
    volatility_30d NUMERIC(8,4),
    return_30d     NUMERIC(8,4),
    beta_vs_spy    NUMERIC(8,4),
    sharpe_ratio   NUMERIC(8,4),
    UNIQUE(asset_id, trade_date)
);

-- ────────────────────────────────────────────────────────────
-- 2. PORTFOLIO & SIMULATION LAYER
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS trading_days (
    trading_day_id SERIAL PRIMARY KEY,
    trade_date     DATE UNIQUE NOT NULL,
    macro_bias     VARCHAR(20),
    risk_environment VARCHAR(20),
    strategy_type  VARCHAR(50),
    total_capital  NUMERIC(10,2) DEFAULT 100.00,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS allocations (
    allocation_id         BIGSERIAL PRIMARY KEY,
    trading_day_id        INT REFERENCES trading_days(trading_day_id),
    asset_id              INT REFERENCES assets(asset_id),
    allocation_dollars    NUMERIC(10,2) CHECK (allocation_dollars >= 10),
    allocation_percentage NUMERIC(5,2),
    conviction_score      NUMERIC(4,2),
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS executions (
    execution_id    BIGSERIAL PRIMARY KEY,
    allocation_id   INT REFERENCES allocations(allocation_id),
    execution_price NUMERIC(12,4),
    shares          NUMERIC(18,6),
    executed_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ────────────────────────────────────────────────────────────
-- 3. PERFORMANCE & RISK
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS daily_portfolio_performance (
    performance_id      BIGSERIAL PRIMARY KEY,
    trading_day_id      INT REFERENCES trading_days(trading_day_id),
    portfolio_value     NUMERIC(12,2),
    daily_profit_loss   NUMERIC(12,2),
    daily_return_pct    NUMERIC(8,4),
    sharpe_ratio        NUMERIC(8,4),
    max_drawdown        NUMERIC(8,4),
    risk_exposure_score NUMERIC(5,2),
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS benchmark_performance (
    benchmark_id         BIGSERIAL PRIMARY KEY,
    trading_day_id       INT REFERENCES trading_days(trading_day_id),
    benchmark_symbol     VARCHAR(20),
    benchmark_return_pct NUMERIC(8,4),
    benchmark_value      NUMERIC(12,2),
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ────────────────────────────────────────────────────────────
-- 4. AGENT DECISION & AUDIT LAYER
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agent_decisions (
    decision_id    BIGSERIAL PRIMARY KEY,
    trading_day_id INT REFERENCES trading_days(trading_day_id),
    agent_name     VARCHAR(100),
    decision_json  JSONB,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS risk_violations (
    violation_id          BIGSERIAL PRIMARY KEY,
    trading_day_id        INT REFERENCES trading_days(trading_day_id),
    violation_type        VARCHAR(100),
    violation_description TEXT,
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ────────────────────────────────────────────────────────────
-- 5. AGENT MEMORY (PINECONE MIRROR)
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agent_memory_log (
    memory_id              BIGSERIAL PRIMARY KEY,
    trading_day_id         INT REFERENCES trading_days(trading_day_id),
    lesson_learned         TEXT,
    mistake_identified     TEXT,
    performance_summary    TEXT,
    embedding_reference_id VARCHAR(100),
    created_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ────────────────────────────────────────────────────────────
-- 6. STRATEGY FRAMEWORK
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS strategies (
    strategy_id   SERIAL PRIMARY KEY,
    strategy_name VARCHAR(100) UNIQUE,
    description   TEXT,
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS strategy_performance_summary (
    summary_id           BIGSERIAL PRIMARY KEY,
    strategy_id          INT REFERENCES strategies(strategy_id),
    cumulative_return    NUMERIC(10,4),
    average_daily_return NUMERIC(8,4),
    volatility           NUMERIC(8,4),
    sharpe_ratio         NUMERIC(8,4),
    max_drawdown         NUMERIC(8,4),
    last_updated         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ────────────────────────────────────────────────────────────
-- INDEXES
-- ────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_market_prices_date    ON market_prices(trade_date);
CREATE INDEX IF NOT EXISTS idx_market_prices_asset   ON market_prices(asset_id);
CREATE INDEX IF NOT EXISTS idx_asset_metrics_date    ON asset_metrics(trade_date);
CREATE INDEX IF NOT EXISTS idx_allocations_day       ON allocations(trading_day_id);
CREATE INDEX IF NOT EXISTS idx_executions_alloc      ON executions(allocation_id);
CREATE INDEX IF NOT EXISTS idx_agent_decisions_day   ON agent_decisions(trading_day_id);
CREATE INDEX IF NOT EXISTS idx_agent_decisions_name  ON agent_decisions(agent_name);
CREATE INDEX IF NOT EXISTS idx_risk_violations_day   ON risk_violations(trading_day_id);

-- ────────────────────────────────────────────────────────────
-- SEED: Core strategies
-- ────────────────────────────────────────────────────────────

INSERT INTO strategies (strategy_name, description) VALUES
    ('momentum',  'Buy recent outperformers aligned with macro trend'),
    ('defensive', 'Shift to bonds and low-volatility ETFs when VIX is elevated'),
    ('balanced',  'Mixed equity and fixed-income for neutral macro environments'),
    ('rotation',  'Rotate into strongest sectors based on relative momentum')
ON CONFLICT (strategy_name) DO NOTHING;
