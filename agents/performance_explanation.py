"""
Agent 6: Performance & Explanation Agent
Evaluates portfolio at market close. Computes Sharpe, drawdown, benchmark comparison.
Writes to: daily_portfolio_performance, benchmark_performance, agent_memory_log.
Also updates strategy_performance_summary.
"""
import time
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from config.agent_config import get_llm, AGENT_PROMPTS
from config.logging_config import get_logger
from tools.market_data import get_current_price, get_benchmark_data
from tools.risk_metrics import calculate_sharpe, calculate_drawdown

log = get_logger("agents.performance_explanation")


class BenchmarkResult(BaseModel):
    return_pct: float
    outperformed: bool


class PerformanceOutput(BaseModel):
    portfolio_return: float
    total_value: float
    pnl: float
    benchmark_comparison: Dict[str, BenchmarkResult]
    risk_metrics: Dict[str, float]
    lessons: List[str]
    explanation_summary: str


class PerformanceExplanationAgent:
    def __init__(self, llm=None):
        self.llm = llm or get_llm(temperature=0, provider="huggingface")
        self.parser = JsonOutputParser(pydantic_object=PerformanceOutput)

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", AGENT_PROMPTS["performance_explanation"] + "\n\n{format_instructions}"),
            ("user", """Portfolio positions (entry data with stop/target levels):
{positions}

Current/closing prices (from yfinance):
{current_prices}

Stop-loss / profit-target outcomes:
{stop_target_outcomes}

Computed metrics:
- Total portfolio value: ${total_value:.2f}
- P&L: ${pnl:.2f}
- Portfolio return: {portfolio_return:.4f}%

Benchmark performance today:
{benchmark_data}

Risk metrics:
- Sharpe ratio: {sharpe_ratio}
- Max drawdown: {max_drawdown}

Analyze performance, explain what worked and what didn't, and extract 1-3 lessons for future sessions.""")
        ])

        self.chain = self.prompt | self.llm | self.parser

    def evaluate(
        self,
        executions: List[Dict],
        trading_day_id: Optional[int] = None,
    ) -> Dict:
        """
        Evaluate portfolio performance at market close.

        Args:
            executions: List of trade records (symbol, price, shares, invested)
            trading_day_id: DB trading_day_id for storing results

        Returns:
            PerformanceOutput dict
        """
        start = time.time()
        budget = 100.0

        # Fetch current prices (all from yfinance)
        current_prices = {}
        for exe in executions:
            symbol = exe.get("symbol")
            price = get_current_price(symbol)
            current_prices[symbol] = price

        # Compute portfolio value
        # For positions already stopped-out/target-hit intraday, use the locked-in exit_price
        total_value = 0.0
        for exe in executions:
            symbol     = exe.get("symbol")
            shares     = float(exe.get("shares", 0))
            status     = exe.get("status", "active")
            exit_price = exe.get("exit_price")
            if status in ("stopped_out", "target_hit") and exit_price:
                total_value += shares * exit_price
            else:
                price = current_prices.get(symbol)
                if price:
                    total_value += shares * price

        pnl = total_value - budget
        portfolio_return = (pnl / budget) * 100

        daily_return = portfolio_return / 100
        sharpe = calculate_sharpe([daily_return])
        drawdown = calculate_drawdown([daily_return])

        benchmarks = get_benchmark_data()

        positions_str = "\n".join([
            f"  {exe['symbol']}: entry=${exe.get('price', 0):.4f}, "
            f"shares={exe.get('shares', 0):.6f}, invested=${exe.get('invested', 0):.2f}, "
            f"stop=${exe.get('stop_loss_price', 'N/A')}, target=${exe.get('profit_target_price', 'N/A')}"
            for exe in executions
        ])
        current_prices_str = "\n".join([
            f"  {sym}: current=${price:.4f}" if price else f"  {sym}: price unavailable"
            for sym, price in current_prices.items()
        ])
        benchmark_str = "\n".join([
            f"  {sym}: return={data.get('return_pct', 'N/A')}%"
            for sym, data in benchmarks.items()
        ])

        # Evaluate whether each position hit its stop or target
        outcome_lines = []
        for exe in executions:
            sym        = exe.get("symbol")
            status     = exe.get("status", "active")
            exit_price = exe.get("exit_price")
            exit_reason = exe.get("exit_reason")
            entry      = exe.get("price", 0)

            if status == "stopped_out" and exit_price:
                pct = (exit_price - entry) / entry * 100 if entry else 0
                outcome_lines.append(
                    f"  {sym}: STOPPED OUT intraday @ ${exit_price:.4f} "
                    f"({pct:.2f}%) — reason: {exit_reason}"
                )
            elif status == "target_hit" and exit_price:
                pct = (exit_price - entry) / entry * 100 if entry else 0
                outcome_lines.append(
                    f"  {sym}: TARGET HIT intraday @ ${exit_price:.4f} "
                    f"(+{pct:.2f}%) — reason: {exit_reason}"
                )
            else:
                # Active position — check live price vs stop/target
                current = current_prices.get(sym)
                stop    = exe.get("stop_loss_price")
                target  = exe.get("profit_target_price")
                if current and stop and target:
                    if current <= stop:
                        outcome_lines.append(f"  {sym}: STOP HIT EOD (${current:.4f} ≤ stop ${stop:.4f})")
                    elif current >= target:
                        outcome_lines.append(f"  {sym}: TARGET HIT EOD (${current:.4f} ≥ target ${target:.4f})")
                    else:
                        pct_to_stop   = (current - stop)   / stop   * 100
                        pct_to_target = (target - current) / current * 100
                        outcome_lines.append(
                            f"  {sym}: in-range (${current:.4f}) — "
                            f"{pct_to_stop:.1f}% above stop, {pct_to_target:.1f}% to target"
                        )
                else:
                    outcome_lines.append(f"  {sym}: no stop/target data")
        stop_target_str = "\n".join(outcome_lines) if outcome_lines else "  (no stop/target data)"

        result = self.chain.invoke({
            "positions": positions_str,
            "current_prices": current_prices_str,
            "stop_target_outcomes": stop_target_str,
            "total_value": total_value,
            "pnl": pnl,
            "portfolio_return": portfolio_return,
            "benchmark_data": benchmark_str,
            "sharpe_ratio": sharpe,
            "max_drawdown": drawdown["max_drawdown"],
            "format_instructions": self.parser.get_format_instructions(),
        })

        if trading_day_id:
            self._store_to_db(
                result=result,
                trading_day_id=trading_day_id,
                total_value=total_value,
                pnl=pnl,
                portfolio_return=portfolio_return,
                sharpe=sharpe,
                drawdown=drawdown,
                benchmarks=benchmarks,
                risk_exposure_score=result.get("risk_metrics", {}).get("risk_exposure_score"),
            )

        result["_duration_ms"] = int((time.time() - start) * 1000)
        return result

    def _store_to_db(
        self,
        result: Dict,
        trading_day_id: int,
        total_value: float,
        pnl: float,
        portfolio_return: float,
        sharpe: float,
        drawdown: Dict,
        benchmarks: Dict,
        risk_exposure_score: Optional[float],
    ) -> None:
        """
        Write to:
        - daily_portfolio_performance  (1 row)
        - benchmark_performance        (1 row per benchmark)
        - strategy_performance_summary (upsert for today's strategy)
        """
        try:
            from config.database import SessionLocal
            from db.models import (
                DailyPortfolioPerformance, BenchmarkPerformance,
                TradingDay, Strategy, StrategyPerformanceSummary,
            )

            db = SessionLocal()
            try:
                is_first_run = False

                # 1. daily_portfolio_performance — upsert (update if exists, insert if new)
                existing_perf = db.query(DailyPortfolioPerformance).filter_by(
                    trading_day_id=trading_day_id
                ).first()
                if existing_perf:
                    # Re-run: update in place, preserve historical record integrity
                    existing_perf.portfolio_value     = round(total_value, 2)
                    existing_perf.daily_profit_loss   = round(pnl, 2)
                    existing_perf.daily_return_pct    = round(portfolio_return, 4)
                    existing_perf.sharpe_ratio        = round(sharpe, 4)
                    existing_perf.max_drawdown        = round(drawdown["max_drawdown"], 4)
                    existing_perf.risk_exposure_score = round(risk_exposure_score, 2) if risk_exposure_score else None
                else:
                    # First run: insert new record
                    is_first_run = True
                    db.add(DailyPortfolioPerformance(
                        trading_day_id=trading_day_id,
                        portfolio_value=round(total_value, 2),
                        daily_profit_loss=round(pnl, 2),
                        daily_return_pct=round(portfolio_return, 4),
                        sharpe_ratio=round(sharpe, 4),
                        max_drawdown=round(drawdown["max_drawdown"], 4),
                        risk_exposure_score=round(risk_exposure_score, 2) if risk_exposure_score else None,
                    ))

                # 2. benchmark_performance — upsert per symbol
                for sym, data in benchmarks.items():
                    ret_pct = data.get("return_pct")
                    price = data.get("price")
                    if ret_pct is None:
                        continue
                    existing_bench = db.query(BenchmarkPerformance).filter_by(
                        trading_day_id=trading_day_id, benchmark_symbol=sym
                    ).first()
                    if existing_bench:
                        existing_bench.benchmark_return_pct = round(ret_pct, 4)
                        existing_bench.benchmark_value = round(price, 2) if price else None
                    else:
                        db.add(BenchmarkPerformance(
                            trading_day_id=trading_day_id,
                            benchmark_symbol=sym,
                            benchmark_return_pct=round(ret_pct, 4),
                            benchmark_value=round(price, 2) if price else None,
                        ))

                # 3. strategy_performance_summary — only accumulate on first run
                # Re-runs only update sharpe/drawdown to avoid double-counting cumulative return
                td = db.query(TradingDay).filter_by(trading_day_id=trading_day_id).first()
                if td and td.strategy_type:
                    strategy = db.query(Strategy).filter_by(
                        strategy_name=td.strategy_type, is_active=True
                    ).first()
                    if strategy:
                        summary = (
                            db.query(StrategyPerformanceSummary)
                            .filter_by(strategy_id=strategy.strategy_id)
                            .order_by(StrategyPerformanceSummary.summary_id.desc())
                            .first()
                        )
                        if summary:
                            if is_first_run:
                                # Only add to cumulative return on first EOD run for this day
                                prev_ret = float(summary.cumulative_return or 0)
                                summary.cumulative_return = round(prev_ret + portfolio_return, 4)
                            # Always update risk metrics (re-runs recalculate these correctly)
                            summary.sharpe_ratio = round(sharpe, 4)
                            summary.max_drawdown = round(drawdown["max_drawdown"], 4)
                        else:
                            db.add(StrategyPerformanceSummary(
                                strategy_id=strategy.strategy_id,
                                cumulative_return=round(portfolio_return, 4),
                                average_daily_return=round(portfolio_return, 4),
                                sharpe_ratio=round(sharpe, 4),
                                max_drawdown=round(drawdown["max_drawdown"], 4),
                            ))

                db.commit()
            finally:
                db.close()
        except Exception as e:
            log.error("[PerformanceAgent] DB store failed: %s", e)
            print(f"  [PerformanceAgent] ERROR storing to DB: {e}")
