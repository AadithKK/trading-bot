import logging
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

class TradeLogger:
    def __init__(self, trade_log_file: str = 'data/trade_log.csv', runs_file: str = 'data/runs.json'):
        self.trade_log_file = trade_log_file
        self.runs_file = runs_file
        self._ensure_files()

    def _ensure_files(self):
        """Create files if they don't exist."""
        Path('data').mkdir(exist_ok=True)

        # Create trade log CSV with headers if it doesn't exist
        if not Path(self.trade_log_file).exists():
            with open(self.trade_log_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'symbol', 'action', 'shares', 'entry_price',
                    'exit_price', 'realized_pnl', 'realized_pnl_percent',
                    'signal_score', 'confidence', 'close_reason', 'holding_days'
                ])

        # Create runs file if it doesn't exist
        if not Path(self.runs_file).exists():
            with open(self.runs_file, 'w') as f:
                json.dump([], f)

    def log_closed_trade(self, trade: Dict):
        """Log a closed trade to CSV."""
        try:
            entry_date = datetime.fromisoformat(trade['entry_date'])
            exit_date = datetime.fromisoformat(trade['exit_date'])
            holding_days = (exit_date - entry_date).days

            with open(self.trade_log_file, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    trade['exit_date'],
                    trade['symbol'],
                    'BUY',
                    round(trade['shares'], 4),
                    trade['entry_price'],
                    trade['exit_price'],
                    trade['realized_pnl'],
                    trade['realized_pnl_percent'],
                    trade.get('confidence', 0),
                    trade.get('confidence', 0),
                    trade.get('close_reason', 'unknown'),
                    holding_days
                ])
        except Exception as e:
            logging.error(f"Failed to log trade: {str(e)}")

    def log_run(self, run_data: Dict):
        """Log a completed run."""
        try:
            with open(self.runs_file, 'r') as f:
                runs = json.load(f)

            runs.append({
                'timestamp': datetime.now().isoformat(),
                'symbols_scanned': run_data.get('symbols_scanned', 0),
                'signals_generated': run_data.get('signals_generated', 0),
                'trades_opened': run_data.get('trades_opened', 0),
                'trades_closed': run_data.get('trades_closed', 0),
                'portfolio_equity': run_data.get('portfolio_equity', 0),
                'ai_available': run_data.get('ai_available', False),
                'status': run_data.get('status', 'completed')
            })

            with open(self.runs_file, 'w') as f:
                json.dump(runs, f, indent=2)

        except Exception as e:
            logging.error(f"Failed to log run: {str(e)}")


def setup_logging(config: dict):
    """Configure logging."""
    log_file = config['logging']['log_file']
    log_level = config['logging']['level']

    Path('logs').mkdir(exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )

    return logging.getLogger(__name__)
