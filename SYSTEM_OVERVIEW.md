# AI Agentic Trading Simulation System — Overview

## What Is This System?

This is an **AI-powered paper trading simulator**. Every day it:
1. Reads the news and checks market conditions
2. Decides which stocks/ETFs to "buy" with a $100 budget
3. Executes simulated trades at real market prices
4. At end of day, evaluates performance and learns from it

All money is simulated — no real trades are placed. The goal is to test AI-driven investment decision making using real market data.

---

## The 6 Agents (The Brain)

The system uses 6 AI agents that work in sequence, like an investment team:

### Agent 1 — Macro Intelligence
**"What's the mood of the market today?"**

- Reads today's financial news headlines from Polygon.io
- Recalls what strategies worked well in recent days (via memory)
- Outputs a market bias: **Bullish** (optimistic), **Bearish** (pessimistic), or **Neutral**
- Also flags the risk environment: **Risk-On** (investors are confident), **Risk-Off** (investors are cautious), or **Mixed**

*Example output: "Neutral bias, Risk-Off environment — Fed rate uncertainty is the dominant theme today."*

---

### Agent 2 — Market Scanner
**"Which assets are worth looking at today?"**

- Scans real market data: top S&P 500 movers (normal mode) or defensive large-caps — consumer staples, healthcare, utilities (defensive mode)
- Filters out illiquid stocks (daily trading < $50M) and penny stocks (< $5)
- Checks Polygon.io news sentiment for each stock (positive/negative/neutral)
- Returns up to **10 candidate stocks** with momentum and volatility scores
- **No ETFs or bond funds** — only individual stocks

*Example output: "NVDA (positive sentiment, strong momentum), JNJ (defensive, low volatility), AAPL (tech strength)"*

---

### Agent 3 — Strategy Agent
**"Which 5 assets should we actually invest in?"**

- Picks the best 5 assets from the 10 candidates
- Considers the macro bias (e.g., if bearish → favour bonds over stocks)
- Checks which strategies have historically made money (from the database)
- Ensures diversification — no single sector exceeds 40% of selection
- Picks a strategy type: **Momentum**, **Defensive**, **Balanced**, or **Rotation**

*Example output: "Defensive strategy — BND 40%, TLT 25%, XLP 15%, IEF 10%, LQD 10%"*

---

### Agent 4 — Risk & Allocation Agent
**"How much money goes into each asset?"**

- Allocates exactly **$100** across the 5 selected assets
- Assets with higher volatility get less money (less risky sizing)
- Assets with higher conviction scores get more money
- Hard rules enforced:
  - Minimum $10 per asset
  - Maximum 5 assets
  - Total must equal exactly $100
- Flags any asset where the potential gain doesn't justify the risk (reward:risk < 2:1)

*Example output: "BND: $40, TLT: $25, XLP: $15, IEF: $10, LQD: $10"*

---

### Agent 5 — Execution Agent
**"Place the trades at real prices."**

- Fetches live prices from Yahoo Finance (no guessing)
- Calculates shares: `shares = dollars_allocated / current_price`
- Sets automatic safety levels for each trade:
  - **Stop-Loss**: 6% below entry price (cuts losses)
  - **Profit Target**: 12% above entry price (locks in gains)
- Saves all trades to the database with status `active`

*Example output: "Bought 0.53 shares of BND @ $74.94, stop-loss @ $70.44, target @ $84.01"*

---

### Agent 6 — Performance & Explanation Agent
**"How did we do today?"**

- Runs at end of day (EOD Evaluate button)
- For positions stopped-out or target-hit intraday, uses the **locked-in exit price** (not EOD price) for accurate P&L
- For active positions, fetches current prices from Yahoo Finance
- Compares performance against benchmarks (SPY, QQQ, DIA, IVV)
- Calculates risk metrics: Sharpe Ratio, Max Drawdown
- Writes a plain-English explanation of what worked and what didn't
- Stores lessons learned for future use

*Example output: "Portfolio +0.11% vs SPY +0.73%. AMD stopped out intraday @ $102.50 (−6.82%). Key lesson: energy and utilities showed weak momentum — avoid in neutral macro environments."*

---

## Safety Guards

Four automatic safety systems prevent bad decisions:

| Guard | What It Does |
|-------|-------------|
| **VIX Guard** | If market fear index > 25, switches to defensive mode (consumer staples, healthcare, utilities stocks only) |
| **Allocation Validator** | Enforces the $100 budget, $10 minimum, and 5-asset maximum — overrides the AI if it breaks rules |
| **Fallback Handler** | If any agent crashes or fails, the whole day is skipped safely — no bad trades |
| **Intraday Monitor** | Checks live prices every 15 minutes during market hours (9:30 AM–4 PM ET); automatically marks positions as stopped-out or target-hit when thresholds are crossed |

---

## Memory & Learning

The system remembers past performance and improves over time:

- **Pinecone (Vector Memory)**: Stores daily records as searchable memories. Agent 1 can recall "what worked 3 days ago when the macro was similar to today."
- **Strategy Tracker (Database)**: Tracks which strategies (momentum, defensive, etc.) have the best cumulative return and Sharpe ratio over time. Agent 3 favours proven strategies.
- **Lessons Learned**: Agent 6 extracts 1–3 lessons each day (e.g., "avoid bonds when Fed is dovish") and stores them for future reference.

---

## Data Sources

| Data | Source | Used By |
|------|--------|---------|
| Stock prices & history | Yahoo Finance (yfinance) | Agents 2, 4, 5, 6 |
| Market news & sentiment | Polygon.io API | Agents 1, 2 |
| VIX (fear index) | Yahoo Finance | VIX Guard |
| Historical performance | PostgreSQL database | Agents 1, 3 |
| Past trading lessons | Pinecone vector store | Agents 1, 3 |

---

## Key Rules & Limits

| Parameter | Value | Meaning |
|-----------|-------|---------|
| Daily budget | $100 | Total simulated capital per day |
| Max assets | 5 | Can hold at most 5 positions |
| Min per asset | $10 | Smallest allocation allowed |
| Stop-loss | 6% below entry | Auto-exit if price drops too much |
| Profit target | 12% above entry | Auto-exit when profit goal is reached |
| VIX threshold | 35 | Above this → blended defensive/growth mode |
| Min reward:risk | 2:1 | Gain potential must be 2× the loss risk |

---

## The Dashboard

A web interface (runs in your browser) lets you:

- **Run Daily** — triggers Agents 1–5 (morning allocation, takes ~60–90 seconds)
- **Full Day** — triggers all 6 agents including EOD evaluation
- **EOD Evaluate** — runs Agent 6 on the selected date's positions
- **Check Positions** — single-pass intraday check: fetches live prices and marks any stops/targets hit
- **View results** across 3 tabs:
  - *Today's Session* — current positions, P&L, benchmark comparison, charts
  - *Historical Performance* — all past trading days, cumulative stats
  - *Agent Audit Trail* — full log of every agent's decisions in detail

---

## How a Full Day Works (Step by Step)

```
9:25 AM ET — Morning Allocation (automated via cron)
  ↓  VIX check — is the market fearful today?
  ↓  Agent 1 reads the news → decides market mood
  ↓  Agent 2 scans the market → finds 10 candidates
  ↓  Agent 3 picks the best 5 → chooses strategy type
  ↓  Agent 4 allocates $100 → sizes each position
  ↓  Agent 5 executes trades → real prices, real shares
       All positions saved with status = "active"

9:30 AM–4:00 PM ET — Intraday Monitor (automated via cron, every 15 min)
  ↓  Fetches live price for each active position
  ↓  Price ≤ stop-loss?  → mark stopped_out, lock in exit_price
  ↓  Price ≥ target?     → mark target_hit, lock in exit_price
  ↓  Otherwise           → log distance to stop/target, continue

4:05 PM ET — EOD Evaluation (automated via cron)
  ↓  Agent 6 checks prices (uses exit_price for resolved positions)
  ↓  Calculates realistic P&L → stopped positions capped at stop price
  ↓  Compares vs SPY, QQQ, DIA benchmarks
  ↓  Writes explanation + lessons learned
  ↓  Updates strategy performance stats
  ↓  Saves memory to Pinecone for tomorrow
```

---

## Deployment

- **Local**: Runs on your Mac, connects to local PostgreSQL
- **Cloud (EC2)**: Deployed on AWS EC2 (Ubuntu), accessible via browser at the server's public IP
- The dashboard runs as a background service on EC2 — starts automatically when the server boots

### Automated Schedule (EC2 Cron — weekdays only)

| Time (ET) | Time (UTC) | Action |
|-----------|------------|--------|
| 9:25 AM | 14:25 UTC | Run Daily — agents 1–5, morning allocation |
| 9:31 AM | 14:31 UTC | Start Monitor — checks positions every 15 min until 4 PM |
| 4:05 PM | 21:05 UTC | EOD Evaluate — Agent 6 calculates final P&L |

All output is logged to `/opt/trading-sim-ai/logs/cron.log`.

### CLI Commands

| Command | What It Does |
|---------|-------------|
| `python main.py --run-daily` | Morning allocation (Agents 1–5) |
| `python main.py --evaluate-only` | EOD evaluation (Agent 6) |
| `python main.py --check-positions` | Single-pass stop/target check |
| `python main.py --monitor` | Loop every 15 min, 9:30 AM–4 PM ET |
| `python main.py --monitor --interval 5` | Loop every 5 minutes |
| `python main.py --status` | Show recent trading sessions |

---

*This system demonstrates how multiple AI agents can collaborate on financial decision-making, with real data, hard safety constraints, intraday risk management, and continuous learning — all without risking real money.*
