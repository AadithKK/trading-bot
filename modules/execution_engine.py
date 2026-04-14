"""
Execution Engine Module
Simulates paper trade execution locally using portfolio.json as the source of truth.
No broker API required — all state is managed in the data directory.
"""

import json
import logging
import math
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DEFAULT_PORTFOLIO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "portfolio.json"
)


def load_portfolio(path: str = DEFAULT_PORTFOLIO_PATH) -> dict:
    """Load portfolio from JSON. Creates a fresh $300 portfolio if the file is missing."""
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    # First-run default
    logger.info("portfolio.json not found — creating default $300 portfolio")
    portfolio = {
        "cash": 300.0,
        "starting_balance": 300.0,
        "open_positions": [],
        "total_trades": 0,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    save_portfolio(portfolio, path)
    return portfolio


def save_portfolio(portfolio: dict, path: str = DEFAULT_PORTFOLIO_PATH) -> None:
    """Persist portfolio state to disk."""
    portfolio["last_updated"] = datetime.now(timezone.utc).isoformat()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(portfolio, f, indent=2)


def calculate_shares(position_size_usd: float, price: float) -> float:
    """Convert dollar amount to share quantity (fractional OK for paper trading)."""
    if price <= 0:
        return 0.0
    return round(position_size_usd / price, 6)


def apply_pre_trade_checks(
    trade: dict, portfolio: dict, config: dict
) -> tuple[bool, str]:
    """
    Validate a proposed trade before execution.
    Returns (is_valid, reason_if_rejected).
    """
    action = trade.get("action", "").upper()
    symbol = trade.get("symbol", "")
    position_size = trade.get("position_size_usd", 0)
    acc = config["account"]

    if action == "HOLD":
        return False, "HOLD — no execution needed"

    if action not in ("BUY", "SELL"):
        return False, f"Unknown action '{action}'"

    if action == "BUY":
        # Check cash availability
        if portfolio["cash"] < position_size:
            return False, f"Insufficient cash (have ${portfolio['cash']:.2f}, need ${position_size:.2f})"

        # Check position limit
        if len(portfolio["open_positions"]) >= acc["max_open_positions"]:
            return False, f"Max open positions ({acc['max_open_positions']}) already reached"

        # Check for duplicate symbol
        existing = [p["symbol"] for p in portfolio["open_positions"]]
        if symbol in existing:
            return False, f"Position in {symbol} already open"

        # Validate position size range
        if position_size < acc["min_trade_size_usd"] or position_size > acc["max_trade_size_usd"]:
            return (
                False,
                f"Position size ${position_size:.2f} outside allowed range "
                f"(${acc['min_trade_size_usd']}–${acc['max_trade_size_usd']})",
            )

    if action == "SELL":
        existing_symbols = [p["symbol"] for p in portfolio["open_positions"]]
        if symbol not in existing_symbols:
            return False, f"No open position in {symbol} to sell"

    return True, "OK"


def execute_buy(
    trade: dict,
    portfolio: dict,
    snapshot: dict,
    config: dict,
    portfolio_path: str = DEFAULT_PORTFOLIO_PATH,
) -> dict | None:
    """
    Execute a BUY order. Deducts cash, creates position entry.
    Returns the trade record dict, or None on failure.
    """
    symbol = trade["symbol"]
    position_size = trade["position_size_usd"]
    slippage = config["execution"]["slippage_pct"]
    entry_price = round(snapshot["price"] * (1 + slippage), 4)
    quantity = calculate_shares(position_size, entry_price)

    if quantity <= 0:
        logger.warning(f"{symbol}: BUY rejected — zero quantity calculated")
        return None

    position = {
        "symbol": symbol,
        "quantity": quantity,
        "entry_price": entry_price,
        "position_size_usd": position_size,
        "entry_timestamp": datetime.now(timezone.utc).isoformat(),
        "signal_strength": trade.get("confidence", 0),
        "reason": trade.get("reason", ""),
    }

    portfolio["cash"] = round(portfolio["cash"] - position_size, 4)
    portfolio["open_positions"].append(position)
    portfolio["total_trades"] += 1
    save_portfolio(portfolio, portfolio_path)

    logger.info(
        f"BUY {symbol}: {quantity:.4f} shares @ ${entry_price} "
        f"(size=${position_size}, cash remaining=${portfolio['cash']:.2f})"
    )

    return {
        "symbol": symbol,
        "action": "BUY",
        "entry_price": entry_price,
        "exit_price": None,
        "quantity": quantity,
        "position_size_usd": position_size,
        "pnl_usd": None,
        "pnl_pct": None,
        "signal_strength": trade.get("confidence", 0),
        "signal_direction": snapshot.get("trend", ""),
        "volatility": snapshot.get("volatility", ""),
        "rsi_at_entry": snapshot.get("rsi", 0),
        "trend_at_entry": snapshot.get("trend", ""),
        "volume_spike": snapshot.get("volume_spike", False),
        "claude_confidence": trade.get("confidence", 0),
        "claude_reason": trade.get("reason", ""),
        "outcome": "open",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def execute_sell(
    trade: dict,
    portfolio: dict,
    snapshot: dict,
    config: dict,
    portfolio_path: str = DEFAULT_PORTFOLIO_PATH,
) -> dict | None:
    """
    Execute a SELL order. Closes existing position, returns cash + P&L.
    Returns the closed trade record dict, or None on failure.
    """
    symbol = trade["symbol"]
    slippage = config["execution"]["slippage_pct"]
    exit_price = round(snapshot["price"] * (1 - slippage), 4)

    # Find the open position
    position = None
    for pos in portfolio["open_positions"]:
        if pos["symbol"] == symbol:
            position = pos
            break

    if position is None:
        logger.warning(f"{symbol}: SELL rejected — no open position found")
        return None

    quantity = position["quantity"]
    entry_price = position["entry_price"]
    proceeds = round(quantity * exit_price, 4)
    cost = round(quantity * entry_price, 4)
    pnl_usd = round(proceeds - cost, 4)
    pnl_pct = round((pnl_usd / cost) * 100, 4) if cost != 0 else 0.0
    outcome = "win" if pnl_usd >= 0 else "loss"

    portfolio["cash"] = round(portfolio["cash"] + proceeds, 4)
    portfolio["open_positions"] = [
        p for p in portfolio["open_positions"] if p["symbol"] != symbol
    ]
    save_portfolio(portfolio, portfolio_path)

    logger.info(
        f"SELL {symbol}: {quantity:.4f} shares @ ${exit_price} "
        f"P&L=${pnl_usd:+.4f} ({pnl_pct:+.2f}%) — {outcome.upper()}"
    )

    return {
        "symbol": symbol,
        "action": "SELL",
        "entry_price": entry_price,
        "exit_price": exit_price,
        "quantity": quantity,
        "position_size_usd": position["position_size_usd"],
        "pnl_usd": pnl_usd,
        "pnl_pct": pnl_pct,
        "signal_strength": position.get("signal_strength", 0),
        "signal_direction": snapshot.get("trend", ""),
        "volatility": snapshot.get("volatility", ""),
        "rsi_at_entry": snapshot.get("rsi", 0),
        "trend_at_entry": position.get("reason", ""),
        "volume_spike": snapshot.get("volume_spike", False),
        "claude_confidence": trade.get("confidence", 0),
        "claude_reason": trade.get("reason", ""),
        "outcome": outcome,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def process_trades(
    claude_decisions: list[dict],
    snapshots: list[dict],
    portfolio: dict,
    config: dict,
    portfolio_path: str = DEFAULT_PORTFOLIO_PATH,
) -> list[dict]:
    """
    Process all Claude trade decisions. Run pre-checks, execute valid trades.
    Returns a list of executed trade records.
    """
    snapshot_map = {s["symbol"]: s for s in snapshots}
    executed = []

    for trade in claude_decisions:
        symbol = trade.get("symbol", "")
        action = trade.get("action", "HOLD").upper()

        if action == "HOLD":
            logger.info(f"{symbol}: HOLD — no action taken")
            continue

        snapshot = snapshot_map.get(symbol)
        if snapshot is None:
            logger.warning(f"{symbol}: no snapshot available — skipping trade")
            continue

        is_valid, reason = apply_pre_trade_checks(trade, portfolio, config)
        if not is_valid:
            logger.warning(f"{symbol}: trade rejected — {reason}")
            continue

        record = None
        if action == "BUY":
            record = execute_buy(trade, portfolio, snapshot, config, portfolio_path)
        elif action == "SELL":
            record = execute_sell(trade, portfolio, snapshot, config, portfolio_path)

        if record is not None:
            executed.append(record)

    return executed


def get_portfolio_value(portfolio: dict, snapshots: list[dict]) -> float:
    """
    Mark-to-market portfolio value = cash + sum of (quantity × current_price) per position.
    """
    snapshot_map = {s["symbol"]: s["price"] for s in snapshots}
    positions_value = sum(
        pos["quantity"] * snapshot_map.get(pos["symbol"], pos["entry_price"])
        for pos in portfolio["open_positions"]
    )
    return round(portfolio["cash"] + positions_value, 2)
