"""
Guardrails: deterministic validators that run AFTER LLM output.
These enforce hard financial constraints the LLM cannot override.
"""
import os
from typing import List, Dict, Optional
from config.logging_config import get_logger

log = get_logger("guardrails")


class AllocationError(Exception):
    pass


class AllocationValidator:
    """
    Post-LLM validator for the Risk & Allocation Agent output.
    Enforces all hard constraints on $100 paper trading budget.
    Constraint breaches are logged to risk_violations table.
    """

    BUDGET = float(os.getenv("PAPER_TRADING_BUDGET", "100"))
    MAX_ASSETS = int(os.getenv("MAX_ASSETS", "5"))
    MIN_ALLOCATION = float(os.getenv("MIN_ALLOCATION", "10"))

    @classmethod
    def validate(
        cls,
        allocations: List[Dict],
        trading_day_id: Optional[int] = None,
    ) -> List[Dict]:
        """
        Validate allocation list. Raises AllocationError if any constraint fails.
        Logs each violation to risk_violations if trading_day_id is provided.

        Args:
            allocations: List of {symbol, allocation_dollars, allocation_percentage}
            trading_day_id: If provided, violations are written to DB.

        Returns:
            Validated allocations (with corrected percentages).
        """
        def _log(vtype: str, desc: str):
            if trading_day_id:
                cls._write_violation(trading_day_id, vtype, desc)

        if not allocations:
            desc = "No allocations provided"
            _log("empty_allocation", desc)
            raise AllocationError(desc)

        if len(allocations) > cls.MAX_ASSETS:
            desc = f"Too many assets: {len(allocations)} > max {cls.MAX_ASSETS}"
            _log("max_assets_exceeded", desc)
            raise AllocationError(desc)

        # Check for negatives first (hard fail)
        for a in allocations:
            dollars = float(a.get("allocation_dollars", 0))
            symbol = a.get("symbol", "?")
            if dollars < 0:
                desc = f"{symbol}: negative allocation ${dollars}"
                _log("negative_allocation", desc)
                raise AllocationError(desc)

        # Step 1: Scale budget to BUDGET first (so minimums are easier to satisfy)
        total = sum(float(a["allocation_dollars"]) for a in allocations)
        if total <= 0:
            desc = "All allocations are zero or negative"
            _log("budget_mismatch", desc)
            raise AllocationError(desc)
        if abs(total - cls.BUDGET) > 0.01:
            scale = cls.BUDGET / total
            for a in allocations:
                a["allocation_dollars"] = round(float(a["allocation_dollars"]) * scale, 2)
            total2 = sum(float(a["allocation_dollars"]) for a in allocations)
            residual = round(cls.BUDGET - total2, 2)
            if residual != 0:
                largest = max(allocations, key=lambda x: float(x.get("allocation_dollars", 0)))
                largest["allocation_dollars"] = round(float(largest["allocation_dollars"]) + residual, 2)
            log.warning("[AllocationValidator] Budget scaled from $%.2f → $%.0f (×%.4f)", total, cls.BUDGET, scale)

        # Step 2: Fix any sub-minimum allocations (take from largest)
        for a in allocations:
            dollars = float(a.get("allocation_dollars", 0))
            symbol = a.get("symbol", "?")
            if dollars < cls.MIN_ALLOCATION:
                shortfall = round(cls.MIN_ALLOCATION - dollars, 2)
                largest = max(allocations, key=lambda x: float(x.get("allocation_dollars", 0)))
                if largest["symbol"] == symbol:
                    # Edge case: this IS the largest — should not happen after scaling
                    desc = f"{symbol}: ${dollars} < min ${cls.MIN_ALLOCATION} and is the largest"
                    _log("below_minimum_allocation", desc)
                    raise AllocationError(desc)
                if float(largest.get("allocation_dollars", 0)) - shortfall >= cls.MIN_ALLOCATION:
                    desc = (f"{symbol}: ${dollars:.2f} < min ${cls.MIN_ALLOCATION} "
                            f"— auto-corrected, took ${shortfall:.2f} from {largest['symbol']}")
                    _log("below_minimum_auto_corrected", desc)
                    log.warning("[AllocationValidator] %s", desc)
                    a["allocation_dollars"] = cls.MIN_ALLOCATION
                    largest["allocation_dollars"] = round(
                        float(largest["allocation_dollars"]) - shortfall, 2
                    )
                else:
                    desc = (f"{symbol}: ${dollars:.2f} < min ${cls.MIN_ALLOCATION} "
                            f"— cannot auto-correct (largest {largest['symbol']} only has "
                            f"${float(largest['allocation_dollars']):.2f})")
                    _log("below_minimum_allocation", desc)
                    raise AllocationError(desc)

        # Recompute percentages for accuracy
        for a in allocations:
            a["allocation_percentage"] = round(
                float(a["allocation_dollars"]) / cls.BUDGET * 100, 2
            )

        return allocations

    @staticmethod
    def _write_violation(trading_day_id: int, vtype: str, desc: str) -> None:
        """Write a single violation record. Silently ignores DB errors."""
        try:
            from config.database import SessionLocal
            from db.models import RiskViolation
            db = SessionLocal()
            try:
                db.add(RiskViolation(
                    trading_day_id=trading_day_id,
                    violation_type=vtype,
                    violation_description=desc,
                ))
                db.commit()
            finally:
                db.close()
        except Exception:
            pass


class VIXGuard:
    """
    Checks VIX level and switches to defensive mode if elevated.
    Defensive mode forces bond-only allocation.
    """

    THRESHOLD = float(os.getenv("VIX_DEFENSIVE_THRESHOLD", "35"))

    @classmethod
    def check(cls) -> Dict:
        """
        Returns {vix: float, mode: "normal"|"defensive"}.
        Falls back to normal mode if VIX is unavailable.
        """
        from tools.market_data import get_vix
        vix = get_vix()

        if vix is None:
            log.warning("[VIXGuard] VIX unavailable, defaulting to normal mode.")
            return {"vix": None, "mode": "normal"}

        mode = "defensive" if vix > cls.THRESHOLD else "normal"
        log.info("[VIXGuard] VIX=%.1f → mode=%s", vix, mode)
        return {"vix": vix, "mode": mode}


class FallbackHandler:
    """
    Handles failures in the pipeline gracefully.
    Rule: If a tool fails, do NOT allocate — log and skip the day.
    """

    @staticmethod
    def handle(error: Exception, context: str = "") -> Dict:
        """
        Log the error and return a safe no-trade state.

        Returns:
            {allocated: False, error: str, allocations: []}
        """
        error_msg = f"[FallbackHandler] {context}: {type(error).__name__}: {error}"
        log.error(error_msg)
        return {
            "allocated": False,
            "error": error_msg,
            "allocations": [],
        }
