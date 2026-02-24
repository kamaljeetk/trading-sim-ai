"""
Agentic Trading Simulation System
Entry point for daily trading pipeline.

Usage:
    python main.py --run-daily                     # Morning: agents 1-5
    python main.py --evaluate-only                  # EOD: agent 6 on today's existing session
    python main.py --run-daily --evaluate           # Full day simulation
    python main.py --run-daily --date 2026-02-20    # Backtest specific date
    python main.py --status                         # Show recent sessions from DB
"""
import argparse
import json
import sys
from datetime import date
from config.logging_config import get_logger

log = get_logger("main")


def run_daily(run_evaluation: bool, target_date: str = None):
    print("\n" + "=" * 60)
    print("  AGENTIC TRADING SIMULATION SYSTEM")
    print(f"  Date: {target_date or str(date.today())}")
    print(f"  Mode: {'Full day' if run_evaluation else 'Morning allocation'}")
    print("=" * 60 + "\n")

    from orchestrator.workflow import run_daily as workflow_run
    final_state = workflow_run(
        run_evaluation=run_evaluation,
        target_date=target_date,
    )

    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)

    errors = final_state.get("errors", [])
    if errors:
        print(f"\n  Errors encountered:")
        for e in errors:
            print(f"    - {e}")

    allocations = final_state.get("allocations", [])
    if allocations:
        print(f"\n  Portfolio Allocations ($100 budget):")
        for a in allocations:
            print(
                f"    {a['symbol']:8s} ${float(a['allocation_dollars']):6.2f} "
                f"({float(a['allocation_percentage']):.1f}%)"
            )
        total = sum(float(a["allocation_dollars"]) for a in allocations)
        print(f"    {'TOTAL':8s} ${total:6.2f}")

    executions = final_state.get("executions", [])
    if executions:
        print(f"\n  Executions (real yfinance prices):")
        for exe in executions:
            print(
                f"    {exe['symbol']:8s} @ ${float(exe['price']):.4f}  "
                f"{float(exe['shares']):.6f} shares"
            )

    performance = final_state.get("performance", {})
    if performance:
        print(f"\n  Performance:")
        print(f"    Portfolio return: {performance.get('portfolio_return', 0):.4f}%")
        print(f"    P&L:              ${performance.get('pnl', 0):.2f}")
        print(f"    Total value:      ${performance.get('total_value', 0):.2f}")
        print(f"\n  Summary: {performance.get('explanation_summary', 'N/A')}")

    print("\n  Trading Day ID:", final_state.get("trading_day_id"))
    print("  Mode:      ", final_state.get("mode", "normal"))
    print("  VIX:       ", final_state.get("vix", "N/A"))
    print()

    return final_state


def evaluate_only(target_date: str = None):
    """Run EOD evaluation (agent 6) on an existing trading day session."""
    from config.database import SessionLocal, init_db
    from db.models import TradingDay, Allocation, Execution
    from datetime import date as date_cls

    init_db()
    today = target_date or str(date_cls.today())

    print("\n" + "=" * 60)
    print("  EOD PERFORMANCE EVALUATION")
    print(f"  Date: {today}")
    print("=" * 60 + "\n")

    db = SessionLocal()
    try:
        td = db.query(TradingDay).filter(
            TradingDay.trade_date == today
        ).first()

        if not td:
            print(f"  No trading session found for {today}.")
            print("  Run --run-daily first.")
            return

        trading_day_id = td.trading_day_id
        log.info("[evaluate_only] trading_day_id=%s for %s", trading_day_id, today)

        # Reconstruct executions list from DB
        executions = []
        for alloc in td.allocations:
            exe = alloc.execution
            if not exe:
                continue
            symbol = alloc.asset.symbol if alloc.asset else None
            if not symbol:
                continue
            executions.append({
                "symbol": symbol,
                "price": float(exe.execution_price),
                "shares": float(exe.shares),
                "invested": float(alloc.allocation_dollars),
                "stop_loss_price": float(exe.stop_loss_price) if exe.stop_loss_price else None,
                "profit_target_price": float(exe.profit_target_price) if exe.profit_target_price else None,
            })
    finally:
        db.close()

    if not executions:
        print("  No executions found for this session.")
        print("  Run --run-daily first to generate trades.")
        return

    print(f"  Found {len(executions)} execution(s): {[e['symbol'] for e in executions]}")

    from agents.performance_explanation import PerformanceExplanationAgent
    from tools.pinecone_memory import store_daily_record

    agent = PerformanceExplanationAgent()
    result = agent.evaluate(executions=executions, trading_day_id=trading_day_id)

    performance = result
    print("\n  Performance:")
    print(f"    Portfolio return: {performance.get('portfolio_return', 0):.4f}%")
    print(f"    P&L:              ${performance.get('pnl', 0):.2f}")
    print(f"    Total value:      ${performance.get('total_value', 0):.2f}")
    print(f"\n  Summary: {performance.get('explanation_summary', 'N/A')}")

    # Store to Pinecone
    db2 = SessionLocal()
    try:
        td2 = db2.query(TradingDay).filter_by(trading_day_id=trading_day_id).first()
        record = {
            "date": today,
            "macro_bias": td2.macro_bias if td2 else None,
            "mode": "normal",
            "strategy_type": td2.strategy_type if td2 else None,
            "symbols": [e["symbol"] for e in executions],
            "portfolio_return": performance.get("portfolio_return", 0),
            "lessons": performance.get("lessons", []),
        }
    finally:
        db2.close()

    vector_id = store_daily_record(record, today)
    if vector_id:
        log.info("[evaluate_only] Pinecone memory stored: %s", vector_id)

    print("\n  Evaluation complete.")
    print()


def show_status():
    """Display recent trading days with performance from PostgreSQL."""
    try:
        from config.database import SessionLocal, init_db
        from db.models import TradingDay, DailyPortfolioPerformance, Allocation
        init_db()
        db = SessionLocal()

        days = db.query(TradingDay).order_by(TradingDay.trade_date.desc()).limit(10).all()

        print("\n  Recent Trading Days")
        print("  " + "-" * 85)
        print(f"  {'ID':>4}  {'Date':12}  {'Bias':8}  {'Strategy':14}  {'Assets':7}  {'Return%':8}  {'P&L':8}")
        print("  " + "-" * 85)
        for td in days:
            perf = td.performance
            ret_str = f"{float(perf.daily_return_pct):.2f}%" if perf and perf.daily_return_pct else "N/A"
            pnl_str = f"${float(perf.daily_profit_loss):.2f}" if perf and perf.daily_profit_loss else "N/A"
            alloc_count = len(td.allocations)
            print(
                f"  {td.trading_day_id:>4}  {str(td.trade_date):12}  "
                f"{(td.macro_bias or 'N/A'):8}  "
                f"{(td.strategy_type or 'N/A'):14}  "
                f"{alloc_count:>4} pos  "
                f"{ret_str:8}  {pnl_str}"
            )
        db.close()

        # Strategy summary
        from db.models import Strategy, StrategyPerformanceSummary
        db = SessionLocal()
        print("\n  Strategy Performance Summary")
        print("  " + "-" * 60)
        print(f"  {'Strategy':14}  {'CumulReturn':12}  {'Sharpe':8}  {'MaxDD':8}")
        print("  " + "-" * 60)
        for s in db.query(Strategy).filter_by(is_active=True).all():
            latest = (
                db.query(StrategyPerformanceSummary)
                .filter_by(strategy_id=s.strategy_id)
                .order_by(StrategyPerformanceSummary.summary_id.desc())
                .first()
            )
            if latest:
                print(
                    f"  {s.strategy_name:14}  "
                    f"{float(latest.cumulative_return):.4f}%       "
                    f"{float(latest.sharpe_ratio or 0):.4f}    "
                    f"{float(latest.max_drawdown or 0):.4f}"
                )
        db.close()
    except Exception as e:
        log.error("[main] Error reading DB: %s", e)
        print(f"  Error reading DB: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Agentic Trading Simulation System"
    )
    parser.add_argument(
        "--run-daily", action="store_true",
        help="Run morning allocation pipeline (agents 1-5)"
    )
    parser.add_argument(
        "--evaluate", action="store_true",
        help="Include EOD evaluation when used with --run-daily"
    )
    parser.add_argument(
        "--evaluate-only", action="store_true",
        help="Run EOD evaluation on today's existing session (no re-allocation)"
    )
    parser.add_argument(
        "--date", type=str, default=None,
        help="Target date (ISO format: YYYY-MM-DD). Defaults to today."
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Show recent sessions from database"
    )

    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if getattr(args, "evaluate_only", False):
        evaluate_only(target_date=args.date)
        return

    if not args.run_daily and not args.evaluate:
        parser.print_help()
        print("\n  Example: python main.py --run-daily")
        print("  Example: python main.py --run-daily --evaluate")
        sys.exit(0)

    run_daily(
        run_evaluation=args.evaluate,
        target_date=args.date,
    )


if __name__ == "__main__":
    main()
