"""
Agent 4: Risk & Allocation Agent
Allocates exactly $100 across selected assets with risk-weighted logic.
Post-LLM AllocationValidator enforces all hard constraints.
Precomputed volatility and returns are passed to execution agent via asset_metrics_data.
"""
import time
from typing import Optional, List, Dict, Tuple
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from config.agent_config import get_llm, AGENT_PROMPTS
from config.logging_config import get_logger
from orchestrator.guardrails import AllocationValidator, AllocationError
from tools.market_data import get_historical_data

log = get_logger("agents.risk_allocation")


class AssetAllocation(BaseModel):
    symbol: str
    allocation_dollars: float = Field(ge=10)
    allocation_percentage: float = Field(ge=0, le=100)


class AllocationOutput(BaseModel):
    allocations: List[AssetAllocation]
    risk_exposure_score: float = Field(ge=0, le=1)
    concentration_score: float = Field(ge=0, le=1)


class RiskAllocationAgent:
    def __init__(self, llm=None):
        self.llm = llm or get_llm(temperature=0, provider="openai")
        self.parser = JsonOutputParser(pydantic_object=AllocationOutput)

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", AGENT_PROMPTS["risk_allocation"] + "\n\n{format_instructions}"),
            ("user", """Selected Assets with volatility data:
{assets_with_volatility}

Allocate exactly $100 total.
Higher volatility → lower allocation.
Higher conviction → higher allocation.
Minimum $10 per asset, maximum 5 assets.
All allocation_dollars must sum to exactly 100.""")
        ])

        self.chain = self.prompt | self.llm | self.parser

    def _compute_metrics(self, symbol: str) -> Dict:
        """
        Fetch 30-day history and compute annualized volatility and return.
        Returns {volatility_30d, return_30d} for asset_metrics table.
        """
        try:
            hist = get_historical_data(symbol, period="35d")
            if hist.empty or len(hist) < 5:
                return {"volatility_30d": 0.25, "return_30d": 0.0}

            daily_ret = hist["Close"].pct_change().dropna()
            vol = float(daily_ret.std() * (252 ** 0.5))
            ret_30d = float(
                (hist["Close"].iloc[-1] - hist["Close"].iloc[0]) / hist["Close"].iloc[0]
            )
            return {
                "volatility_30d": round(vol, 4),
                "return_30d": round(ret_30d, 4),
            }
        except Exception:
            return {"volatility_30d": 0.25, "return_30d": 0.0}

    def allocate(
        self,
        selected_assets: List[Dict],
        trading_day_id: Optional[int] = None,
        retry_count: int = 0,
    ) -> Dict:
        """
        Allocate $100 across selected assets, with post-LLM validation.
        Retries once on AllocationError before propagating.

        Returns:
            Validated AllocationOutput dict with added asset_metrics_data key.
        """
        start = time.time()

        # Compute real metrics per asset
        asset_metrics_data: Dict[str, Dict] = {}
        enriched_lines = []
        for a in selected_assets:
            symbol = a["symbol"]
            metrics = self._compute_metrics(symbol)
            asset_metrics_data[symbol] = metrics
            enriched_lines.append(
                f"  {symbol}: conviction={a.get('conviction_score', 0.5):.2f}, "
                f"volatility={metrics['volatility_30d']:.2%}, "
                f"return_30d={metrics['return_30d']:.2%}, "
                f"reason={a.get('strategic_reason', '')}"
            )

        result = self.chain.invoke({
            "assets_with_volatility": "\n".join(enriched_lines),
            "format_instructions": self.parser.get_format_instructions(),
        })

        # Post-LLM deterministic validation
        try:
            validated = AllocationValidator.validate(
                result.get("allocations", []),
                trading_day_id=trading_day_id,
            )
            result["allocations"] = validated
        except AllocationError as e:
            if retry_count < 1:
                log.warning("[RiskAllocationAgent] Validation failed (%s), retrying...", e)
                return self.allocate(selected_assets, trading_day_id, retry_count + 1)
            raise

        result["asset_metrics_data"] = asset_metrics_data

        # Reward:risk check — flag assets where expected return < 2× stop risk (6%)
        STOP_RISK = 0.06
        MIN_RR = 2.0
        reward_risk_warnings = []
        for a in selected_assets:
            symbol = a["symbol"]
            expected_return = asset_metrics_data.get(symbol, {}).get("return_30d", 0.0)
            rr_ratio = expected_return / STOP_RISK if expected_return > 0 else 0.0
            if rr_ratio < MIN_RR:
                reward_risk_warnings.append({
                    "symbol": symbol,
                    "reward_risk_ratio": round(rr_ratio, 2),
                    "note": (
                        f"{symbol} R:R={rr_ratio:.1f} below 2:1 target "
                        f"(30d return={expected_return*100:.1f}% vs 6% stop risk)"
                    ),
                })
        if reward_risk_warnings:
            log.warning(
                "[RiskAllocationAgent] %d asset(s) with R:R < 2:1: %s",
                len(reward_risk_warnings),
                [w["symbol"] for w in reward_risk_warnings],
            )
        result["reward_risk_warnings"] = reward_risk_warnings

        result["_duration_ms"] = int((time.time() - start) * 1000)
        return result
