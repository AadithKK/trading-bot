"""
Main Trading Cycle Scripts

Designed to work with a scheduled Claude Code agent (no API key needed).
The agent runs these two commands each morning:

  1. python main.py --generate-signals
     Fetches market data, scores all symbols, saves qualified signals to
     data/pending_signals.json for Claude to review.

  2. python main.py --execute-decisions
     Reads Claude's decisions from data/pending_decisions.json and
     executes the trades, logs them, runs feedback analysis.

Manual testing (bypasses market hours check):
  python main.py --generate-signals --force
  python main.py --execute-decisions --force
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

import pytz

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH        = os.path.join(BASE_DIR, "config.json")
PORTFOLIO_PATH     = os.path.join(BASE_DIR, "data", "portfolio.json")
TRADE_LOG_PATH     = os.path.join(BASE_DIR, "data", "trade_log.csv")
FEEDBACK_PATH      = os.path.join(BASE_DIR, "data", "feedback_report.json")
PENDING_SIGNALS    = os.path.join(BASE_DIR, "data", "pending_signals.json")
PENDING_DECISIONS  = os.path.join(BASE_DIR, "data", "pending_decisions.json")
LOG_PATH           = os.path.join(BASE_DIR, "logs", "system.log")

PATHS = {
    "trade_log": TRADE_LOG_PATH,
    "feedback":  FEEDBACK_PATH,
    "config":    CONFIG_PATH,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def is_trading_day() -> bool:
    """True if today is Mon–Fri in ET."""
    now = datetime.now(pytz.timezone("America/New_York"))
    return now.weekday() < 5


def is_after_close(config: dict) -> bool:
    now = datetime.now(pytz.timezone("America/New_York"))
    return now.hour >= config["market_hours"]["close_hour_et"]


# ---------------------------------------------------------------------------
# Mode 1 — Generate Signals
# Collects market data, scores all symbols, writes pending_signals.json
# ---------------------------------------------------------------------------


def generate_signals_mode(force: bool = False) -> None:
    config = load_config()

    from modules.logger import setup_logging
    setup_logging(LOG_PATH)
    log = logging.getLogger("generate_signals")
    log.info("=" * 60)
    log.info("generate-signals: starting")

    if not force and config["market_hours"].get("check_market_hours", True):
        if not is_trading_day():
            log.info("Weekend — skipping signal generation")
            return
        if is_after_close(config):
            log.info("Market closed for the day — skipping")
            return

    from modules.execution_engine import load_portfolio
    portfolio = load_portfolio(PORTFOLIO_PATH)

    from modules.market_data import collect_all_symbols
    log.info("Fetching market data...")
    snapshots = collect_all_symbols(config)

    if not snapshots:
        log.warning("No market data — cannot generate signals")
        _write_empty_signals(portfolio)
        return

    from modules.signal_engine import generate_signals, filter_by_min_strength
    all_signals = generate_signals(snapshots, config)
    min_strength = config["signal_thresholds"]["min_signal_strength_for_claude"]
    qualified = filter_by_min_strength(all_signals, min_strength)

    # Build the pending_signals file for Claude to read
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "portfolio_summary": {
            "cash": portfolio["cash"],
            "open_count": len(portfolio["open_positions"]),
            "open_positions": [
                {
                    "symbol": p["symbol"],
                    "entry_price": p["entry_price"],
                    "quantity": p["quantity"],
                    "position_size_usd": p["position_size_usd"],
                }
                for p in portfolio["open_positions"]
            ],
        },
        "min_strength_threshold": min_strength,
        "all_signals": all_signals,
        "qualified_signals": qualified,
        "snapshots": {s["symbol"]: s for s in snapshots},
    }

    os.makedirs(os.path.dirname(PENDING_SIGNALS), exist_ok=True)
    with open(PENDING_SIGNALS, "w") as f:
        json.dump(output, f, indent=2)

    log.info(
        f"Signals saved → {len(qualified)}/{len(all_signals)} qualified "
        f"(strength >= {min_strength})"
    )
    log.info(f"Pending signals file: {PENDING_SIGNALS}")

    if qualified:
        log.info("Qualified signals for Claude review:")
        for s in qualified:
            snap = output["snapshots"].get(s["symbol"], {})
            log.info(
                f"  {s['symbol']:5s}  {s['signal']:<8s}  strength={s['strength']}  "
                f"rsi={snap.get('rsi','?')}  trend={snap.get('trend','?')}  "
                f"vol={snap.get('volatility','?')}"
            )
    else:
        log.info("No signals qualified — Claude will see an empty list")


def _write_empty_signals(portfolio: dict) -> None:
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "portfolio_summary": {
            "cash": portfolio["cash"],
            "open_count": len(portfolio["open_positions"]),
            "open_positions": [],
        },
        "qualified_signals": [],
        "all_signals": [],
        "snapshots": {},
    }
    os.makedirs(os.path.dirname(PENDING_SIGNALS), exist_ok=True)
    with open(PENDING_SIGNALS, "w") as f:
        json.dump(output, f, indent=2)


# ---------------------------------------------------------------------------
# Mode 2 — Execute Decisions
# Reads pending_decisions.json written by Claude, executes the trades
# ---------------------------------------------------------------------------


def execute_decisions_mode(force: bool = False) -> None:
    config = load_config()

    from modules.logger import setup_logging, log_trade, update_trade_on_close, log_cycle_summary
    setup_logging(LOG_PATH)
    log = logging.getLogger("execute_decisions")
    log.info("=" * 60)
    log.info("execute-decisions: starting")

    if not force and config["market_hours"].get("check_market_hours", True):
        if not is_trading_day():
            log.info("Weekend — skipping execution")
            return
        if is_after_close(config):
            log.info("Market closed — skipping execution")
            return

    # Load Claude's decisions
    if not os.path.exists(PENDING_DECISIONS):
        log.warning(f"No pending decisions file found at {PENDING_DECISIONS} — nothing to execute")
        return

    with open(PENDING_DECISIONS, "r") as f:
        decisions_data = json.load(f)

    trades = decisions_data.get("trades", [])
    if not trades:
        log.info("Claude provided no trades — HOLD this cycle")
        _print_portfolio_summary(config, log)
        return

    log.info(f"Received {len(trades)} decision(s) from Claude")

    # Load the snapshots that were generated alongside the signals
    snapshots = []
    if os.path.exists(PENDING_SIGNALS):
        with open(PENDING_SIGNALS, "r") as f:
            sigs_data = json.load(f)
        snap_map = sigs_data.get("snapshots", {})
        snapshots = list(snap_map.values())

    if not snapshots:
        log.warning("No snapshot data — cannot determine current prices. Aborting.")
        return

    from modules.execution_engine import load_portfolio, process_trades, get_portfolio_value
    portfolio = load_portfolio(PORTFOLIO_PATH)

    executed = process_trades(trades, snapshots, portfolio, config, PORTFOLIO_PATH)

    for trade in executed:
        log_trade(trade, TRADE_LOG_PATH)
        if trade["action"] == "SELL":
            update_trade_on_close(trade["symbol"], trade, TRADE_LOG_PATH)

    log.info(f"Executed {len(executed)} trade(s)")

    # Clear the decisions file after execution to avoid re-running stale decisions
    os.remove(PENDING_DECISIONS)

    # Reload portfolio after trades
    portfolio = load_portfolio(PORTFOLIO_PATH)
    portfolio_value = get_portfolio_value(portfolio, snapshots)

    # Feedback analysis
    from modules.feedback_analyzer import run_feedback_analysis
    try:
        run_feedback_analysis(config, PATHS)
    except Exception as exc:
        log.warning(f"Feedback analysis error (non-fatal): {exc}")

    # Cycle summary
    log_cycle_summary(
        {
            "symbols_processed": len(snapshots),
            "signals_generated": len(sigs_data.get("all_signals", [])) if os.path.exists(PENDING_SIGNALS) else 0,
            "signals_to_claude": len(sigs_data.get("qualified_signals", [])) if os.path.exists(PENDING_SIGNALS) else 0,
            "trades_executed": len(executed),
            "open_positions": len(portfolio["open_positions"]),
            "cash": portfolio["cash"],
            "portfolio_value": portfolio_value,
        },
        log,
    )


def _print_portfolio_summary(config: dict, log: logging.Logger) -> None:
    from modules.execution_engine import load_portfolio, get_portfolio_value
    portfolio = load_portfolio(PORTFOLIO_PATH)
    snapshots = []
    if os.path.exists(PENDING_SIGNALS):
        with open(PENDING_SIGNALS, "r") as f:
            data = json.load(f)
        snapshots = list(data.get("snapshots", {}).values())
    value = get_portfolio_value(portfolio, snapshots)
    log.info(f"Portfolio: cash=${portfolio['cash']:.2f}  value=${value:.2f}  "
             f"positions={len(portfolio['open_positions'])}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Claude Paper Trading System")
    parser.add_argument(
        "--generate-signals",
        action="store_true",
        help="Collect market data, score signals, write data/pending_signals.json",
    )
    parser.add_argument(
        "--execute-decisions",
        action="store_true",
        help="Read data/pending_decisions.json from Claude and execute trades",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass market hours / weekday check (for testing)",
    )
    args = parser.parse_args()

    if args.generate_signals:
        generate_signals_mode(force=args.force)
    elif args.execute_decisions:
        execute_decisions_mode(force=args.force)
    else:
        parser.print_help()
        print("\nRun with --generate-signals or --execute-decisions")
