"""
Agent 3: Strategy Agent
Selects up to 5 assets from candidates, aligned with macro bias.
"""
import time
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from config.agent_config import get_llm, AGENT_PROMPTS


class SelectedAsset(BaseModel):
    symbol: str
    strategic_reason: str
    conviction_score: float = Field(ge=0, le=1)


class StrategyOutput(BaseModel):
    selected_assets: List[SelectedAsset] = Field(max_length=5)
    strategy_type: str = Field(description="momentum | defensive | balanced | rotation")
    diversification_score: float = Field(ge=0, le=1)


class StrategyAgent:
    def __init__(self, llm=None):
        self.llm = llm or get_llm(temperature=0, provider="huggingface")
        self.parser = JsonOutputParser(pydantic_object=StrategyOutput)

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", AGENT_PROMPTS["strategy"] + "\n\n{format_instructions}"),
            ("user", """Macro Signals:
- Bias: {macro_bias}
- Risk Environment: {risk_environment}
- Dominant Themes: {dominant_themes}
- Sector Strengths: {sectors_strength}

Historical Strategy Performance (ranked by cumulative return — use this to pick strategy_type):
{strategy_perf_context}

Best-Performing Historical Days (replicate these patterns when macro aligns):
{best_days_context}

Candidate Assets (max 10):
{candidates}

Select up to 5 assets. Prioritize:
1. The strategy_type with the BEST historical Sharpe ratio (from performance above)
2. Assets in sectors that appeared in best-performing days
3. Higher conviction_score for assets matching winning historical patterns
4. No single sector > 40% of selection
5. In defensive mode: prefer defensive sector stocks (consumer staples, healthcare, utilities) — NO ETFs or bonds""")
        ])

        self.chain = self.prompt | self.llm | self.parser

    def select(
        self,
        macro_signals: Dict,
        candidates: List[Dict],
        strategy_perf: Optional[List[Dict]] = None,
        best_days: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        Select up to 5 assets from candidates, biased toward historically profitable strategies.

        Args:
            macro_signals: Output from MacroIntelligenceAgent
            candidates: List of candidate dicts from MarketScannerAgent
            strategy_perf: List of {strategy_name, cumulative_return, sharpe_ratio, max_drawdown}
            best_days: List of best-performing historical day records

        Returns:
            StrategyOutput dict
        """
        start = time.time()

        def fmt_candidates(assets: List[Dict]) -> str:
            lines = []
            for a in assets:
                lines.append(
                    f"  {a.get('symbol')}: type={a.get('asset_type')}, "
                    f"momentum={a.get('momentum_score', 0):.2f}, "
                    f"volatility={a.get('volatility_score', 0):.2f}, "
                    f"reason={a.get('reason_for_selection', '')}"
                )
            return "\n".join(lines)

        if strategy_perf:
            perf_lines = []
            for s in sorted(strategy_perf, key=lambda x: float(x.get("sharpe_ratio", 0)), reverse=True):
                ret = float(s.get("cumulative_return", 0))
                sign = "+" if ret >= 0 else ""
                perf_lines.append(
                    f"  {s['strategy_name']}: cumulative={sign}{ret:.2f}%, "
                    f"sharpe={float(s.get('sharpe_ratio', 0)):.4f}, "
                    f"max_drawdown={float(s.get('max_drawdown', 0)):.4f}"
                )
            strategy_perf_str = "\n".join(perf_lines) or "No strategy history yet."
        else:
            strategy_perf_str = "No strategy history yet — pick strategy based on macro signals alone."

        if best_days:
            best_lines = []
            for r in best_days[:3]:
                best_lines.append(
                    f"  {r.get('date')}: return={r.get('portfolio_return', 0):.2f}%, "
                    f"strategy={r.get('strategy_type')}, macro={r.get('macro_bias')}, "
                    f"assets={', '.join(r.get('symbols', []))}, "
                    f"lessons={'; '.join(r.get('lessons', []))}"
                )
            best_days_str = "\n".join(best_lines) or "No profitable days recorded yet."
        else:
            best_days_str = "No profitable days recorded yet."

        valid_symbols = {c.get("symbol", "").upper() for c in candidates}

        result = self.chain.invoke({
            "macro_bias": macro_signals.get("macro_bias", "neutral"),
            "risk_environment": macro_signals.get("risk_environment", "mixed"),
            "dominant_themes": ", ".join(macro_signals.get("dominant_themes", [])),
            "sectors_strength": str(macro_signals.get("sectors_strength", {})),
            "strategy_perf_context": strategy_perf_str,
            "best_days_context": best_days_str,
            "candidates": fmt_candidates(candidates),
            "format_instructions": self.parser.get_format_instructions(),
        })

        # Hard filter: remove any symbol the LLM invented that wasn't in our candidate list
        original_count = len(result.get("selected_assets", []))
        result["selected_assets"] = [
            a for a in result.get("selected_assets", [])
            if a.get("symbol", "").upper() in valid_symbols
        ]
        removed = original_count - len(result["selected_assets"])
        if removed:
            print(f"  [StrategyAgent] Filtered out {removed} hallucinated symbol(s) not in candidate list")

        duration_ms = int((time.time() - start) * 1000)
        result["_duration_ms"] = duration_ms
        return result
