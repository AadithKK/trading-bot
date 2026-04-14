"""
Logger Module
Handles system logging (logs/system.log + stdout) and persistent trade
history in data/trade_log.csv.
"""

import csv
import logging
import os
from datetime import datetime, timezone

TRADE_LOG_COLUMNS = [
    "timestamp",
    "symbol",
    "action",
    "entry_price",
    "exit_price",
    "quantity",
    "position_size_usd",
    "pnl_usd",
    "pnl_pct",
    "signal_strength",
    "signal_direction",
    "volatility",
    "rsi_at_entry",
    "trend_at_entry",
    "volume_spike",
    "claude_confidence",
    "claude_reason",
    "outcome",
]


def setup_logging(log_path: str) -> logging.Logger:
    """
    Configure root logger with FileHandler + StreamHandler.
    Returns the root logger so callers can get named children via logging.getLogger(__name__).
    """
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    log_format = "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Avoid adding duplicate handlers on repeated calls (e.g., tests)
    if not root.handlers:
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(logging.Formatter(log_format, date_format))
        root.addHandler(fh)

        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter(log_format, date_format))
        root.addHandler(sh)

    return root


def log_trade(trade_record: dict, csv_path: str) -> None:
    """
    Append a single trade record to the CSV log.
    Writes the header row only when the file is first created.
    """
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    file_exists = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0

    row = {col: trade_record.get(col, "") for col in TRADE_LOG_COLUMNS}

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TRADE_LOG_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def update_trade_on_close(symbol: str, exit_data: dict, csv_path: str) -> None:
    """
    Find the most recent open trade for `symbol` in the CSV and fill in:
    exit_price, pnl_usd, pnl_pct, outcome.
    Called when a SELL is executed.
    """
    if not os.path.exists(csv_path):
        return

    rows = []
    updated = False

    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (
                not updated
                and row["symbol"] == symbol
                and row["action"] == "BUY"
                and row["outcome"] == "open"
            ):
                row["exit_price"] = exit_data.get("exit_price", "")
                row["pnl_usd"] = exit_data.get("pnl_usd", "")
                row["pnl_pct"] = exit_data.get("pnl_pct", "")
                row["outcome"] = exit_data.get("outcome", "")
                updated = True
            rows.append(row)

    if updated:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=TRADE_LOG_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)


def read_trade_log(csv_path: str):
    """Read the trade log CSV into a pandas DataFrame. Returns None if file missing."""
    try:
        import pandas as pd
        if not os.path.exists(csv_path):
            return None
        df = pd.read_csv(csv_path)
        if df.empty:
            return None
        return df
    except Exception as exc:
        logging.getLogger(__name__).warning(f"Could not read trade log: {exc}")
        return None


def log_cycle_summary(cycle_data: dict, app_logger: logging.Logger) -> None:
    """Log a human-readable summary at the end of each trading cycle."""
    app_logger.info("=" * 60)
    app_logger.info("CYCLE SUMMARY")
    app_logger.info(f"  Symbols processed  : {cycle_data.get('symbols_processed', 0)}")
    app_logger.info(f"  Signals generated  : {cycle_data.get('signals_generated', 0)}")
    app_logger.info(f"  Signals to Claude  : {cycle_data.get('signals_to_claude', 0)}")
    app_logger.info(f"  Trades executed    : {cycle_data.get('trades_executed', 0)}")
    app_logger.info(f"  Open positions     : {cycle_data.get('open_positions', 0)}")
    app_logger.info(f"  Cash               : ${cycle_data.get('cash', 0):.2f}")
    app_logger.info(f"  Portfolio value    : ${cycle_data.get('portfolio_value', 0):.2f}")
    pnl = cycle_data.get('portfolio_value', 300) - 300.0
    app_logger.info(f"  Total P&L          : ${pnl:+.2f}")
    app_logger.info("=" * 60)
