"""
Agent 1: Macro Intelligence Agent (RAG-powered)
Analyzes macroeconomic context using Pinecone memory of recent performance.
"""
import time
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from config.agent_config import get_llm, AGENT_PROMPTS


class MacroSignals(BaseModel):
    macro_bias: str = Field(description="bullish | bearish | neutral")
    risk_environment: str = Field(description="risk_on | risk_off | mixed")
    dominant_themes: List[str] = Field(description="Key macro themes driving markets")
    sectors_strength: Dict[str, str] = Field(
        description="Sector → strong | neutral | weak"
    )
    confidence_score: float = Field(description="Confidence in macro assessment 0-1")


class MacroIntelligenceAgent:
    def __init__(self, llm=None):
        self.llm = llm or get_llm(temperature=0, provider="huggingface")
        self.parser = JsonOutputParser(pydantic_object=MacroSignals)

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", AGENT_PROMPTS["macro_intelligence"] + "\n\n{format_instructions}"),
            ("user", """LIVE MARKET NEWS (from Polygon.io, published today):
{market_headlines}

Recent performance memory (last {n_days} days):
{memory_context}

Historical strategy performance (cumulative stats from all past sessions):
{strategy_perf_context}

Best-performing historical days (for pattern replication):
{best_days_context}

Today's date: {date}

Using the LIVE headlines as the primary signal for today's macro environment,
combined with historical performance memory, output macro signals that MAXIMIZE
profit today. Identify themes in the headlines (earnings, Fed, geopolitics, sector news),
cross-reference with which macro conditions historically yielded the best returns,
and bias your output accordingly.""")
        ])

        self.chain = self.prompt | self.llm | self.parser

    def analyze(
        self,
        memory_context: List[Dict],
        date: str,
        strategy_perf: Optional[List[Dict]] = None,
        best_days: Optional[List[Dict]] = None,
        market_headlines: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        Run macro analysis using live Polygon.io news, Pinecone memory, and DB strategy performance.

        Args:
            memory_context: List of recent daily records from Pinecone
            date: Today's date (ISO string)
            strategy_perf: List of {strategy_name, cumulative_return, sharpe_ratio, max_drawdown}
            best_days: List of best-performing historical day records from Pinecone
            market_headlines: List of {title, published_utc, tickers, overall_sentiment}
                              from Polygon.io — today's live news

        Returns:
            MacroSignals dict
        """
        start = time.time()

        if not memory_context:
            memory_str = "No prior performance data available. Assume neutral macro environment."
        else:
            lines = []
            for r in memory_context:
                ret = r.get('portfolio_return', 0)
                sign = "+" if ret >= 0 else ""
                lines.append(
                    f"- {r.get('date')}: macro={r.get('macro_bias')}, "
                    f"return={sign}{ret:.2f}%, "
                    f"strategy={r.get('strategy_type')}, "
                    f"lessons={'; '.join(r.get('lessons', []))}"
                )
            memory_str = "\n".join(lines)

        if strategy_perf:
            perf_lines = []
            for s in sorted(strategy_perf, key=lambda x: float(x.get("cumulative_return", 0)), reverse=True):
                perf_lines.append(
                    f"  {s['strategy_name']}: cumulative_return={float(s.get('cumulative_return', 0)):.2f}%, "
                    f"sharpe={float(s.get('sharpe_ratio', 0)):.4f}, "
                    f"max_drawdown={float(s.get('max_drawdown', 0)):.4f}"
                )
            strategy_perf_str = "\n".join(perf_lines) or "No strategy history yet."
        else:
            strategy_perf_str = "No strategy history yet."

        if best_days:
            best_lines = []
            for r in best_days[:3]:
                best_lines.append(
                    f"  {r.get('date')}: return={r.get('portfolio_return', 0):.2f}%, "
                    f"strategy={r.get('strategy_type')}, macro={r.get('macro_bias')}, "
                    f"assets={', '.join(r.get('symbols', []))}"
                )
            best_days_str = "\n".join(best_lines) or "No profitable days recorded yet."
        else:
            best_days_str = "No profitable days recorded yet."

        if market_headlines:
            headline_lines = []
            for h in market_headlines[:12]:  # cap at 12 to keep prompt tight
                tickers_str = ", ".join(h.get("tickers", []))
                headline_lines.append(
                    f"  [{h.get('overall_sentiment', 'neutral').upper()}] "
                    f"{h.get('title', '')} "
                    f"({h.get('published_utc', '')})"
                    + (f" | tickers: {tickers_str}" if tickers_str else "")
                )
            market_headlines_str = "\n".join(headline_lines)
        else:
            market_headlines_str = "No live news available (POLYGON_API_KEY not configured)."

        result = self.chain.invoke({
            "market_headlines": market_headlines_str,
            "memory_context": memory_str,
            "n_days": len(memory_context),
            "strategy_perf_context": strategy_perf_str,
            "best_days_context": best_days_str,
            "date": date,
            "format_instructions": self.parser.get_format_instructions(),
        })

        duration_ms = int((time.time() - start) * 1000)
        result["_duration_ms"] = duration_ms
        return result
