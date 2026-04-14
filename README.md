# Claude Paper Trading Bot

A fully automated paper trading system that uses deterministic signal scoring + Claude AI to manage a $300 simulated portfolio. Runs every weekday morning without any manual input.

**Live Dashboard → https://aadithkk.github.io/trading-bot/**

---

## How It Works

Every weekday at **9:20 AM ET**, a scheduled Claude agent wakes up in Anthropic's cloud and runs the full trading cycle automatically. Your PC does not need to be on.

```
9:20 AM ET — Claude agent fires (Anthropic cloud)
    │
    ├─ 1. Fetches live market data (yfinance) for 7 symbols
    │
    ├─ 2. Signal Engine scores each symbol (0–100, no AI)
    │      AAPL, MSFT, NVDA, TSLA, AMZN, META, SPY
    │
    ├─ 3. Only signals with score ≥ 60 go to Claude for review
    │
    ├─ 4. Claude selects 0–3 trades (or HOLDs) using risk rules
    │
    ├─ 5. Trades are paper-executed (simulated, no real money)
    │
    ├─ 6. Results saved to data/portfolio.json + data/trade_log.csv
    │
    └─ 7. GitHub commit pushed → dashboard updates automatically
```

---

## The Two Layers

### Layer 1 — Signal Engine (deterministic, no AI)
Scores every symbol based on technical indicators. Pure math, no guessing.

| Indicator | How it's used |
|---|---|
| RSI (14-day) | Bullish zone: 45–70. Bearish zone: below 55. Extremes (>75 or <25) = neutral. |
| Trend | SMA20 vs SMA50. Price > SMA20 > SMA50 = uptrend. Opposite = downtrend. |
| Volume | Current volume vs 20-day rolling average. >1.5× average = spike. |
| Volatility | ATR(14) / price. Above 3% = high. Below 1% = low. |

**Scoring formula:**
```
Base score:            50
+ Trend alignment:    +30   (signal direction matches trend)
+ RSI in range:       +15
+ Volume spike:       +15
- High volatility:    -25
- Mixed signals:      -20   (contradictory indicators)
─────────────────────────
Max possible:         100
Min possible:           0
```

Only symbols scoring **≥ 60** are passed to Claude. Everything below is filtered out automatically.

### Layer 2 — Claude Filter (AI review)
Claude receives only the pre-scored signals. It does not see raw market data. Its job is risk control, not prediction.

Claude's rules:
- Reject any signal with strength below 70
- Maximum 3 open positions at any time
- Each trade: $6–$15 (2–5% of $300)
- When uncertain → HOLD (capital preservation over profit)
- No leverage, ever

---

## File Structure

```
trading-bot/
│
├── main.py                    # Entry point — two modes:
│                              #   --generate-signals  (Step 1-2 above)
│                              #   --execute-decisions (Step 5-6 above)
│
├── config.json                # All tunable settings (thresholds, weights, etc.)
├── requirements.txt           # Python deps (yfinance, pandas, pytz)
│
├── modules/
│   ├── market_data.py         # Fetches OHLCV from yfinance, computes all indicators
│   ├── signal_engine.py       # Deterministic scoring engine
│   ├── execution_engine.py    # Paper trade simulation (no real broker needed)
│   ├── logger.py              # CSV trade log + system.log
│   └── feedback_analyzer.py  # Win rate analysis, suggests threshold adjustments
│
├── data/
│   ├── portfolio.json         # Live state: cash, open positions, total trades
│   ├── trade_log.csv          # Every trade ever made (entry, exit, P&L, outcome)
│   └── feedback_report.json  # Latest win rate analysis (appears after 10+ trades)
│
├── docs/                      # GitHub Pages dashboard
│   ├── index.html             # Charts, P&L, open positions, recent trades
│   └── data/                  # Mirror of data/ — updated by agent each cycle
│
└── logs/
    └── system.log             # Full log of every cycle (what happened and why)
```

---

## Watchlist

| Symbol | What it is |
|---|---|
| AAPL | Apple |
| MSFT | Microsoft |
| NVDA | Nvidia |
| TSLA | Tesla |
| AMZN | Amazon |
| META | Meta |
| SPY | S&P 500 ETF (market benchmark) |

---

## Account Rules

| Setting | Value |
|---|---|
| Starting balance | $300 |
| Risk per trade | $6–$15 (2–5%) |
| Max open positions | 3 |
| Leverage | Not allowed |
| Trading type | Paper (simulated) |

---

## Feedback Loop

After **10 closed trades**, the system automatically analyzes performance and suggests threshold adjustments:

- If RSI range 60–70 has a low win rate → suggests narrowing the range
- If high-volatility trades consistently lose → suggests increasing the penalty
- If a trend condition underperforms → flags it for review

Suggestions are saved to `data/feedback_report.json` and shown on the dashboard. Adjustments are **not applied automatically** unless you set `auto_apply_adjustments: true` in `config.json`.

---

## Running Manually

If you want to run a cycle yourself (for testing):

```bash
# Install deps (first time only)
pip install -r requirements.txt

# Step 1: Generate and score signals
python main.py --generate-signals --force

# Step 2: Review data/pending_signals.json, then run execution
python main.py --execute-decisions --force
```

The `--force` flag bypasses the weekday/market-hours check.

---

## Tuning the Bot

All thresholds are in `config.json`. Key ones to know:

```json
"signal_thresholds": {
  "rsi_bullish_min": 45,       ← raise to be more selective on RSI
  "rsi_bullish_max": 70,       ← lower to avoid near-overbought signals
  "min_signal_strength_for_claude": 60  ← raise to only send strongest signals
},
"scoring_weights": {
  "high_volatility_penalty": -25  ← increase (more negative) to avoid volatile markets
},
"claude": {
  "min_strength_threshold": 70   ← Claude rejects anything below this
}
```

---

## Scheduled Agent

The daily cycle is handled by a Claude Code scheduled trigger (no local machine needed).
To view or manage the schedule: **https://claude.ai/code/scheduled**
