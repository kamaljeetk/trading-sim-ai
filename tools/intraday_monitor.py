"""
Intraday stop-loss and profit-target monitor.

Queries all active executions for a given trading date, fetches live prices
from yfinance, and marks positions as stopped_out or target_hit in the DB.

Entry points:
    check_positions(target_date)                   — single pass
    run_monitor_loop(target_date, interval_minutes) — polls every N minutes
"""
import time
from datetime import datetime, date as date_cls
from typing import Optional
from zoneinfo import ZoneInfo  # stdlib Python 3.9+

from config.database import SessionLocal, init_db
from config.logging_config import get_logger
from db.models import TradingDay, Allocation, Execution, Asset
from tools.market_data import get_current_price

log = get_logger("tools.intraday_monitor")

ET = ZoneInfo("America/New_York")
MARKET_OPEN  = (9, 30)
MARKET_CLOSE = (16, 0)


# ─── Public API ───────────────────────────────────────────────────────────────

def check_positions(target_date: Optional[str] = None) -> dict:
    """
    Single-pass check of all active positions for target_date.
    Fetches live prices and updates DB for any triggered stops/targets.

    Returns:
        {"checked": int, "triggered": int, "results": [{symbol, action, price}]}
    """
    init_db()
    today = target_date or str(date_cls.today())

    db = SessionLocal()
    try:
        td = db.query(TradingDay).filter(TradingDay.trade_date == today).first()
        if not td:
            log.warning("[IntradayMonitor] No trading session found for %s", today)
            print(f"  [IntradayMonitor] No trading session found for {today}.")
            return {"checked": 0, "triggered": 0, "results": []}

        rows = (
            db.query(Execution, Allocation, Asset)
            .join(Allocation, Execution.allocation_id == Allocation.allocation_id)
            .join(Asset, Allocation.asset_id == Asset.asset_id)
            .filter(Allocation.trading_day_id == td.trading_day_id)
            .filter(Execution.status == "active")
            .all()
        )

        if not rows:
            log.info("[IntradayMonitor] No active positions for %s", today)
            print(f"  [IntradayMonitor] No active positions for {today}.")
            return {"checked": 0, "triggered": 0, "results": []}

        triggered = 0
        results = []
        now_et = datetime.now(ET)

        for exe, alloc, asset in rows:
            symbol = asset.symbol
            current_price = get_current_price(symbol)

            if current_price is None:
                log.warning("[IntradayMonitor] Could not fetch price for %s — skipping", symbol)
                print(f"  [IntradayMonitor] WARNING: Could not fetch price for {symbol} — skipping")
                continue

            stop   = float(exe.stop_loss_price)     if exe.stop_loss_price     else None
            target = float(exe.profit_target_price) if exe.profit_target_price else None
            entry  = float(exe.execution_price)

            action = None

            if stop and current_price <= stop:
                action          = "stopped_out"
                exe.status      = "stopped_out"
                exe.exit_price  = current_price
                exe.exit_time   = now_et
                exe.exit_reason = "stop_loss"
                pct = (current_price - entry) / entry * 100
                print(
                    f"  [IntradayMonitor] STOP HIT   {symbol:8s} "
                    f"${current_price:.4f}  (entry ${entry:.4f}, {pct:.2f}%,  stop ${stop:.4f})"
                )
                log.warning(
                    "[IntradayMonitor] STOP HIT %s @ $%.4f (entry $%.4f, %.2f%%)",
                    symbol, current_price, entry, pct,
                )

            elif target and current_price >= target:
                action          = "target_hit"
                exe.status      = "target_hit"
                exe.exit_price  = current_price
                exe.exit_time   = now_et
                exe.exit_reason = "profit_target"
                pct = (current_price - entry) / entry * 100
                print(
                    f"  [IntradayMonitor] TARGET HIT  {symbol:8s} "
                    f"${current_price:.4f}  (entry ${entry:.4f}, +{pct:.2f}%, target ${target:.4f})"
                )
                log.info(
                    "[IntradayMonitor] TARGET HIT %s @ $%.4f (entry $%.4f, +%.2f%%)",
                    symbol, current_price, entry, pct,
                )

            else:
                pct_to_stop   = (current_price - stop)   / stop   * 100 if stop   else None
                pct_to_target = (target - current_price) / current_price * 100 if target else None
                status_str = (
                    f"  [IntradayMonitor] OK          {symbol:8s} "
                    f"${current_price:.4f}  "
                    f"({pct_to_stop:+.1f}% vs stop, {pct_to_target:.1f}% to target)"
                    if pct_to_stop is not None and pct_to_target is not None
                    else f"  [IntradayMonitor] OK          {symbol:8s} ${current_price:.4f}"
                )
                print(status_str)

            if action:
                triggered += 1
                results.append({"symbol": symbol, "action": action, "price": current_price})

        db.commit()

        print(
            f"\n  [IntradayMonitor] Done — {len(rows)} positions checked, "
            f"{triggered} triggered."
        )
        log.info("[IntradayMonitor] checked=%d triggered=%d", len(rows), triggered)

        return {"checked": len(rows), "triggered": triggered, "results": results}

    finally:
        db.close()


def run_monitor_loop(
    target_date: Optional[str] = None,
    interval_minutes: int = 15,
) -> None:
    """
    Poll check_positions every interval_minutes during market hours (9:30–16:00 ET).
    Exits automatically when all positions are resolved or market closes.
    """
    today_str = target_date or str(date_cls.today())
    print(f"\n  [IntradayMonitor] Starting monitor loop for {today_str}")
    print(f"  [IntradayMonitor] Interval : every {interval_minutes} minutes")
    print(f"  [IntradayMonitor] Window   : 9:30 AM – 4:00 PM ET")
    print(f"  [IntradayMonitor] Press Ctrl+C to stop.\n")

    while True:
        now_et     = datetime.now(ET)
        open_time  = now_et.replace(hour=MARKET_OPEN[0],  minute=MARKET_OPEN[1],  second=0, microsecond=0)
        close_time = now_et.replace(hour=MARKET_CLOSE[0], minute=MARKET_CLOSE[1], second=0, microsecond=0)

        if now_et < open_time:
            wait_secs = int((open_time - now_et).total_seconds())
            print(f"  [IntradayMonitor] Pre-market — waiting {wait_secs // 60}m {wait_secs % 60}s for open...")
            time.sleep(min(wait_secs, interval_minutes * 60))
            continue

        if now_et >= close_time:
            print("  [IntradayMonitor] Market closed (4:00 PM ET). Exiting monitor loop.")
            break

        print(f"\n  [IntradayMonitor] Check at {now_et.strftime('%H:%M:%S ET')}")
        summary = check_positions(today_str)

        if summary["checked"] == 0:
            print("  [IntradayMonitor] No active positions remain. Exiting.")
            break

        next_check  = now_et.timestamp() + interval_minutes * 60
        sleep_until = min(next_check, close_time.timestamp())
        sleep_secs  = max(0, sleep_until - datetime.now(ET).timestamp())
        print(f"  [IntradayMonitor] Next check in {int(sleep_secs // 60)}m {int(sleep_secs % 60)}s")
        time.sleep(sleep_secs)
