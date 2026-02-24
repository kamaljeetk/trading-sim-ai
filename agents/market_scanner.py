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
from tools.market_data import (
    get_top_movers, get_sector_etfs, get_index_data, get_bond_etfs
)
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

Available market data (real prices from yfinance + Polygon.io news sentiment):

TOP MOVERS:
{top_movers}

SECTOR ETFs:
{sector_etfs}

INDEX ETFs:
{index_etfs}

BOND ETFs:
{bond_etfs}

Select up to 10 candidate assets aligned with the macro environment.
Return ONLY symbols that appear in the data above.
Prioritize assets with POSITIVE news sentiment and strong momentum.
Penalize assets with NEGATIVE news sentiment unless technical momentum is exceptional.""")
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

        # Fetch real market data
        movers = get_top_movers(n=15)
        sectors = get_sector_etfs()
        indices = get_index_data()
        bonds = get_bond_etfs()

        # In defensive mode, bias toward bonds
        if mode == "defensive":
            movers = []  # skip individual stocks

        # Collect all symbols for batch sentiment fetch
        all_symbols = (
            [a["symbol"] for a in movers]
            + [a["symbol"] for a in sectors]
            + [a["symbol"] for a in indices]
            + [a["symbol"] for a in bonds]
        )
        sentiment_data = get_batch_sentiment(all_symbols) if all_symbols else {}

        def sentiment_label(score: float) -> str:
            if score > 0.15:
                return "positive"
            if score < -0.15:
                return "negative"
            return "neutral"

        def fmt_assets(assets: List[Dict]) -> str:
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
                liq_str = f"${liq:.0f}M/day" if liq is not None else "ETF/high-liq"
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

        result = self.chain.invoke({
            "macro_bias": macro_signals.get("macro_bias", "neutral"),
            "risk_environment": macro_signals.get("risk_environment", "mixed"),
            "dominant_themes": ", ".join(macro_signals.get("dominant_themes", [])),
            "top_movers": fmt_assets(movers),
            "sector_etfs": fmt_assets(sectors),
            "index_etfs": fmt_assets(indices),
            "bond_etfs": fmt_assets(bonds),
            "format_instructions": self.parser.get_format_instructions(),
        })

        duration_ms = int((time.time() - start) * 1000)
        result["_duration_ms"] = duration_ms
        return result
