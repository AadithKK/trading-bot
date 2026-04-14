# Local Paper Trading Bot MVP

A fully local, desktop-based paper trading system using Ollama for AI decision support.

## 📊 Live Dashboard

**View your portfolio from anywhere:**  
🔗 **[Trading Bot Dashboard](https://aadithkk.github.io/trading-bot/)**

Real-time monitoring of your portfolio, open positions, trades, and signals. Auto-updates every 60 seconds. Mobile responsive dark theme dashboard.

## Quick Start

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Start Ollama Server

In PowerShell:
```powershell
ollama run gemma2:9b
```

(Or your preferred model - config.json has "gemma2:9b" as default)

### 3. Run a Manual Test

```bash
python main.py --status
```

This shows your current portfolio.

```bash
python main.py --force
```

This runs a full trading cycle (ignores market hours for testing).

## Configuration

All settings are in `config.json`:

- **trading**: Position sizing, stop loss, take profit, max positions
- **signals**: RSI ranges, momentum thresholds, volume requirements
- **thresholds**: Indicator calculations, minimum bars for analysis
- **market**: Trading hours, timezone, day checks
- **watchlist**: Core symbols, dynamic sources, AI review cap
- **ollama**: Ollama server URL, model, timeout settings
- **feedback**: When to trigger performance analysis
- **scheduler**: Run time, enabled/disabled
- **github**: Auto-push settings, repo path
- **logging**: Log level, file locations

## Project Structure

```
trading-bot-local/
├── main.py                 # Entry point
├── config.json             # All settings
├── requirements.txt        # Python dependencies
├── run_bot.bat             # Windows Task Scheduler script
├── README.md               # This file
│
├── modules/
│   ├── market_data.py      # yfinance fetcher + watchlist
│   ├── signal_engine.py    # Deterministic indicator scoring
│   ├── ai_decision.py      # Ollama integration
│   ├── execution.py        # Paper trading engine
│   ├── logger.py           # Trade logging + runs tracking
│   └── __init__.py         # Empty, for imports
│
├── data/                   # Persistent data (created at runtime)
│   ├── portfolio.json      # Current portfolio state
│   ├── trade_log.csv       # All closed trades
│   ├── signals.json        # Latest signal scores
│   ├── watchlist.json      # Current watchlist
│   ├── runs.json           # Run history
│   └── performance.json    # Performance metrics (future)
│
├── logs/                   # Log files
│   ├── system.log          # Main system log
│   └── scheduler.log       # Task scheduler log
│
└── docs/                   # Dashboard (for GitHub Pages)
    └── (generated at runtime)
```

## How It Works

### Trading Cycle

1. **Market Data Fetch** - Grab OHLCV data for watchlist symbols
2. **Signal Engine** - Score each symbol 0-100 (deterministic, no AI)
3. **Trade Filter** - Keep only strongest signals (score ≥ 75 for AI review)
4. **AI Review** - Ollama reviews top 10-15 candidates, decides BUY/SKIP
5. **Paper Execution** - Simulate trades, track stop loss / take profit
6. **Position Updates** - Check if any open trades hit exits
7. **Logging** - Record all trades, run stats
8. **Portfolio Save** - Update portfolio.json with new state

### Signal Scoring

Each symbol gets scored based on:

- **Trend** (+30): Price > SMA20 > SMA50 (uptrend required)
- **RSI** (+15): In valid range (50-65 for longs)
- **Momentum** (+15): Recent 5-day move 2-6%
- **Volume** (+15): Current volume ≥ 1.3x average
- **Volatility** (-25): ATR too high (> 4% of price)
- **Relative Strength** (+10): Outperforming SPY

**Score ranges:**
- 0-64: Rejected
- 65-74: Weak, AI may skip
- 75-84: Strong, AI will review
- 85+: Very strong, auto-approved

### AI Decision Layer

Ollama (local, Gemma model) acts as a **risk reviewer**:
- Reviews only the strongest signals
- Decides BUY or SKIP
- Suggests position size (5-10% of account)
- Suggests stop loss and take profit levels
- Falls back to rules if unavailable

## Running the Bot

### Manual Run

```bash
# Check portfolio status
python main.py --status

# Run cycle (ignoring market hours)
python main.py --force

# Run with default config
python main.py
```

### Scheduled Runs (Windows Task Scheduler)

1. Open Task Scheduler (taskscheduler.msc)
2. Create Basic Task
3. Name: "Trading Bot Daily"
4. Trigger: Daily, 8:20 AM (before market open)
5. Action: Start program: `C:\path\to\run_bot.bat`
6. Conditions: Only run if user is logged on (optional)

**Note:** The bot will skip non-trading days automatically.

## Portfolio Files

### portfolio.json
Live portfolio state:
- Starting balance
- Current cash
- Equity
- Open positions
- Closed positions history
- Win rate, P&L tracking

### trade_log.csv
Every closed trade:
- Entry/exit dates
- Prices
- P&L
- Close reason
- Holding period

### signals.json
Latest signal scores from last run

### runs.json
History of all cycle runs with stats

## Customization

### Change Stop Loss / Take Profit
Edit `config.json`:
```json
"trading": {
  "stop_loss_percent": 3,
  "take_profit_percent": 6
}
```

### Add/Remove Symbols
Edit `config.json` -> `watchlist` -> `core_symbols`

### Adjust Signal Thresholds
Edit `config.json` -> `signals`

Example: Make RSI range stricter:
```json
"rsi_valid_min": 55,
"rsi_valid_max": 60
```

### Change Ollama Model
```json
"ollama": {
  "model": "mistral:latest"
}
```

Make sure the model is installed: `ollama run mistral:latest`

## Troubleshooting

### Ollama Not Connecting
- Check Ollama is running: `ollama list` in terminal
- Verify base URL in config.json (default: `http://localhost:11434`)
- Check logs/system.log for connection errors

### No Data Fetched
- Check internet connection
- Verify symbols are valid (AAPL, MSFT, etc.)
- Check logs for yfinance errors

### Trades Not Executing
- Check cash balance (need ≥ 5% of equity available)
- Check max open positions (default: 3)
- Look for reject reasons in logs

### Portfolio Not Saving
- Check write permissions on `data/` folder
- Ensure disk space available
- Check logs for file write errors

## Future Upgrades

This MVP is designed for easy expansion:

1. **Real Broker Integration** - Replace paper execution with live broker API
2. **Feedback Loop** - Auto-suggest threshold adjustments after 20+ trades
3. **Dashboard** - GitHub Pages site showing live performance
4. **Advanced Indicators** - More sophisticated signal generation
5. **Risk Management** - Portfolio-level risk controls, correlation analysis
6. **Multiple Timeframes** - Intraday trading support

The core structure remains unchanged - just swap out modules as needed.

## Support

Check `logs/system.log` for detailed error messages.

Run `python main.py --status` to verify bot health.

Inspect `data/` folder files to debug data issues.

## License

MIT - Use and modify as needed.
