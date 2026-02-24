"""
Agent 5: Execution & Simulation Agent
Retrieves real prices from yfinance, calculates shares.
Stores assets → allocations → executions in PostgreSQL.
STRICT: No price guessing. All prices from yfinance only.
"""
import time
from datetime import date as date_type
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from config.agent_config import get_llm, AGENT_PROMPTS
from config.logging_config import get_logger
from tools.market_data import get_current_price
from orchestrator.guardrails import FallbackHandler

log = get_logger("agents.execution_simulation")


class TradeRecord(BaseModel):
    symbol: str
    price: float
    shares: float
    invested: float


class ExecutionOutput(BaseModel):
    executions: List[TradeRecord]
    total_invested: float


class ExecutionSimulationAgent:
    def __init__(self, llm=None):
        self.llm = llm or get_llm(temperature=0, provider="openai")
        self.parser = JsonOutputParser(pydantic_object=ExecutionOutput)

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", AGENT_PROMPTS["execution_simulation"] + "\n\n{format_instructions}"),
            ("user", """Validated allocations with REAL current prices (from yfinance):
{allocations_with_prices}

For each allocation:
- shares = round(allocation_dollars / price, 6)
- invested = round(shares * price, 2)
- total_invested must equal sum of all invested amounts

Do NOT modify prices. Use exactly the prices provided.""")
        ])

        self.chain = self.prompt | self.llm | self.parser

    def execute(
        self,
        allocations: List[Dict],
        trading_day_id: Optional[int] = None,
        asset_metrics_data: Optional[Dict] = None,
    ) -> Dict:
        """
        Simulate trade execution with real yfinance prices.

        Args:
            allocations: Validated list from RiskAllocationAgent
            trading_day_id: DB trading_day_id for storage
            asset_metrics_data: {symbol: {volatility_30d, return_30d}} from risk agent

        Returns:
            ExecutionOutput dict
        """
        start = time.time()

        # Fetch real prices — fail fast if any are unavailable
        prices = {}
        failed = []
        for a in allocations:
            symbol = a["symbol"]
            price = get_current_price(symbol)
            if price is None:
                failed.append(symbol)
            else:
                prices[symbol] = price

        if failed:
            return FallbackHandler.handle(
                Exception(f"Cannot retrieve prices for: {failed}"),
                context="ExecutionSimulationAgent",
            )

        lines = []
        for a in allocations:
            symbol = a["symbol"]
            dollars = float(a["allocation_dollars"])
            price = prices[symbol]
            lines.append(f"  {symbol}: allocation=${dollars:.2f}, price=${price:.4f}")

        result = self.chain.invoke({
            "allocations_with_prices": "\n".join(lines),
            "format_instructions": self.parser.get_format_instructions(),
        })

        # Enrich executions with stop-loss and profit-target (deterministic, not LLM)
        # Stop loss: 6% below entry; Profit target: 12% above entry (2:1 reward:risk)
        for exe in result.get("executions", []):
            symbol = exe.get("symbol")
            if symbol and symbol in prices:
                entry = prices[symbol]
                exe["stop_loss_price"] = round(entry * 0.94, 4)
                exe["profit_target_price"] = round(entry * 1.12, 4)

        # Persist to PostgreSQL
        if trading_day_id:
            self._store_to_db(
                executions=result.get("executions", []),
                trading_day_id=trading_day_id,
                allocations=allocations,
                prices=prices,
                asset_metrics_data=asset_metrics_data or {},
            )

        duration_ms = int((time.time() - start) * 1000)
        result["_duration_ms"] = duration_ms
        result["allocated"] = True
        return result

    def _store_to_db(
        self,
        executions: List[Dict],
        trading_day_id: int,
        allocations: List[Dict],
        prices: Dict[str, float],
        asset_metrics_data: Dict,
    ) -> None:
        """
        Data flow per asset:
        1. Upsert into assets → get asset_id
        2. Store today's price into market_prices
        3. Store computed metrics into asset_metrics
        4. Insert into allocations → get allocation_id
        5. Insert into executions
        """
        try:
            from config.database import SessionLocal
            from db.helpers import upsert_asset, store_market_price, upsert_asset_metrics
            from db.models import Allocation, Execution

            today = date_type.today()
            alloc_map = {a["symbol"]: a for a in allocations}

            db = SessionLocal()
            try:
                # Clear any existing allocations+executions for this trading day
                # (prevents duplicates when re-running the same date)
                existing = db.query(Allocation).filter_by(trading_day_id=trading_day_id).all()
                for alloc in existing:
                    db.query(Execution).filter_by(allocation_id=alloc.allocation_id).delete()
                db.query(Allocation).filter_by(trading_day_id=trading_day_id).delete()
                db.flush()

                for exe in executions:
                    symbol = exe.get("symbol")
                    alloc = alloc_map.get(symbol, {})
                    price = prices.get(symbol)
                    metrics = asset_metrics_data.get(symbol, {})

                    # 1. Upsert asset
                    asset_id = upsert_asset(
                        db,
                        symbol=symbol,
                        asset_type=alloc.get("asset_type", "etf"),
                        sector=alloc.get("sector"),
                    )

                    # 2. Store market price
                    store_market_price(db, asset_id, today, close_price=price)

                    # 3. Store asset metrics (volatility from risk agent)
                    if metrics:
                        upsert_asset_metrics(
                            db,
                            asset_id=asset_id,
                            trade_date=today,
                            volatility_30d=metrics.get("volatility_30d"),
                            return_30d=metrics.get("return_30d"),
                        )

                    # 4. Insert allocation
                    allocation_record = Allocation(
                        trading_day_id=trading_day_id,
                        asset_id=asset_id,
                        allocation_dollars=alloc.get("allocation_dollars"),
                        allocation_percentage=alloc.get("allocation_percentage"),
                        conviction_score=alloc.get("conviction_score"),
                    )
                    db.add(allocation_record)
                    db.flush()  # get allocation_id

                    # 5. Insert execution
                    db.add(Execution(
                        allocation_id=allocation_record.allocation_id,
                        execution_price=exe.get("price"),
                        shares=exe.get("shares"),
                        stop_loss_price=exe.get("stop_loss_price"),
                        profit_target_price=exe.get("profit_target_price"),
                    ))

                db.commit()
            finally:
                db.close()
        except Exception as e:
            log.error("[ExecutionAgent] DB store failed: %s", e)
