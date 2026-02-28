"""
Agent 2: Market Scanner Agent
Identifies candidate assets using real yfinance data + Polygon.io news sentiment.
"""
import time
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from config.agent_config import get_llm, AGENT_PROMPTS
from tools.market_data import get_top_movers, get_defensive_stocks
from tools.news_sentiment import get_batch_sentiment


class CandidateAsset(BaseModel):
    symbol: str
    asset_type: str = Field(description="stock | etf | bond_etf | index")
    reason_for_selection: str
    momentum_score: float = Field(ge=0, le=1)
    volatility_score: float = Field(ge=0, le=1)


class ScannerOutput(BaseModel):
    candidates: List[CandidateAsset] = Field(max_length=10)


class MarketScannerAgent:
    def __init__(self, llm=None):
        self.llm = llm or get_llm(temperature=0, provider="huggingface")
        self.parser = JsonOutputParser(pydantic_object=ScannerOutput)

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", AGENT_PROMPTS["market_scanner"] + "\n\n{format_instructions}"),
            ("user", """Macro context:
- Bias: {macro_bias}
- Risk environment: {risk_environment}
- Dominant themes: {dominant_themes}
- Mode: {mode}

Available individual stocks (real prices from yfinance + Polygon.io news sentiment):

{stock_list}

Select up to 10 candidate stocks aligned with the macro environment.
Return ONLY symbols that appear in the data above.
Prioritize stocks with POSITIVE news sentiment and strong momentum.
Penalize stocks with NEGATIVE news sentiment unless technical momentum is exceptional.
In defensive mode, prefer low-volatility stocks from consumer staples, healthcare, or utilities.""")
        ])

        self.chain = self.prompt | self.llm | self.parser

    def scan(self, macro_signals: Dict, mode: str = "normal") -> Dict:
        """
        Scan markets and return candidate assets with news sentiment enrichment.

        Args:
            macro_signals: Output from MacroIntelligenceAgent
            mode: "normal" or "defensive" (from VIXGuard)

        Returns:
            ScannerOutput dict with candidates list
        """
        start = time.time()

        # Fetch real stock data
        # Defensive mode: blend top movers + defensive stocks (more risk-tolerant)
        if mode == "defensive":
            stocks = get_top_movers(n=10) + get_defensive_stocks(n=10)
            # deduplicate by symbol
            seen = set()
            stocks = [s for s in stocks if not (s["symbol"] in seen or seen.add(s["symbol"]))]
        else:
            stocks = get_top_movers(n=20)

        # Collect all symbols for batch sentiment fetch
        all_symbols = [a["symbol"] for a in stocks]
        sentiment_data = get_batch_sentiment(all_symbols) if all_symbols else {}

        def sentiment_label(score: float) -> str:
            if score > 0.15:
                return "positive"
            if score < -0.15:
                return "negative"
            return "neutral"

        def fmt_stocks(assets: List[Dict]) -> str:
            if not assets:
                return "  (none)"
            lines = []
            for a in assets:
                sym = a["symbol"]
                sent = sentiment_data.get(sym, {})
                s_score = sent.get("sentiment_score", 0.0)
                s_label = sentiment_label(s_score)
                s_articles = sent.get("headline_count", 0)
                top_headline = sent.get("top_headlines", [""])[0][:80] if sent.get("top_headlines") else "no recent news"

                liq = a.get("avg_daily_value_m")
                liq_str = f"${liq:.0f}M/day" if liq is not None else "high-liq"
                line = (
                    f"  {sym}: price=${a.get('price', 'N/A')}, "
                    f"liquidity={liq_str}, "
                    f"momentum={a.get('momentum_score', 'N/A')}, "
                    f"volatility={a.get('volatility_score', 'N/A')}, "
                    f"news_sentiment={s_label}({s_score:+.2f}, {s_articles} articles), "
                    f"headline=\"{top_headline}\""
                )
                lines.append(line)
            return "\n".join(lines)

        valid_symbols = {a["symbol"].upper() for a in stocks}

        result = self.chain.invoke({
            "macro_bias": macro_signals.get("macro_bias", "neutral"),
            "risk_environment": macro_signals.get("risk_environment", "mixed"),
            "dominant_themes": ", ".join(macro_signals.get("dominant_themes", [])),
            "mode": mode,
            "stock_list": fmt_stocks(stocks),
            "format_instructions": self.parser.get_format_instructions(),
        })

        # Hard filter: remove any symbol the LLM invented that wasn't in our stock list
        original_count = len(result.get("candidates", []))
        result["candidates"] = [
            c for c in result.get("candidates", [])
            if c.get("symbol", "").upper() in valid_symbols
        ]
        removed = original_count - len(result["candidates"])
        if removed:
            print(f"  [MarketScanner] Filtered out {removed} hallucinated symbol(s) not in stock universe")

        duration_ms = int((time.time() - start) * 1000)
        result["_duration_ms"] = duration_ms
        return result
