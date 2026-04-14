import logging
import json
from datetime import datetime
from typing import Dict, List, Optional
import uuid

logger = logging.getLogger(__name__)

class PaperExecutionEngine:
    def __init__(self, config: dict, portfolio: 'Portfolio'):
        self.config = config
        self.portfolio = portfolio

    def execute_trade(self, decision: Dict, current_price: float) -> Optional[Dict]:
        """Execute a paper trade based on AI decision."""
        symbol = decision['symbol']
        action = decision['action']

        if action != 'BUY':
            logger.debug(f"{symbol}: SKIP (AI decision)")
            return None

        # Check constraints
        if len(self.portfolio.open_positions) >= self.config['trading']['max_open_positions']:
            logger.warning(f"{symbol}: rejected - max positions reached")
            return None

        position_size_dollars = (
            self.portfolio.get_cash() *
            decision['position_size_percent'] / 100
        )

        if position_size_dollars < 100:
            logger.warning(f"{symbol}: rejected - position too small (${position_size_dollars:.2f})")
            return None

        shares = position_size_dollars / current_price
        stop_loss_price = current_price * (1 - decision['stop_loss_percent'] / 100)
        take_profit_price = current_price * (1 + decision['take_profit_percent'] / 100)

        trade = {
            'trade_id': str(uuid.uuid4())[:8],
            'symbol': symbol,
            'entry_date': datetime.now().isoformat(),
            'entry_price': round(current_price, 2),
            'shares': round(shares, 4),
            'allocated_capital': round(position_size_dollars, 2),
            'stop_loss_price': round(stop_loss_price, 2),
            'take_profit_price': round(take_profit_price, 2),
            'stop_loss_percent': decision['stop_loss_percent'],
            'take_profit_percent': decision['take_profit_percent'],
            'confidence': decision['confidence'],
            'ai_reasoning': decision['reasoning'],
            'status': 'open',
            'unrealized_pnl': 0,
            'unrealized_pnl_percent': 0
        }

        self.portfolio.add_open_position(trade)
        logger.info(f"{symbol}: BUY {trade['shares']:.4f} @ ${trade['entry_price']} (${position_size_dollars:.2f})")

        return trade

    def update_positions(self, current_prices: Dict[str, float]) -> List[Dict]:
        """Update open positions with current prices and check exits."""
        closed_trades = []

        for trade in self.portfolio.open_positions[:]:
            symbol = trade['symbol']
            if symbol not in current_prices:
                continue

            current_price = current_prices[symbol]
            unrealized_pnl = (current_price - trade['entry_price']) * trade['shares']
            unrealized_pnl_percent = (current_price - trade['entry_price']) / trade['entry_price'] * 100

            trade['unrealized_pnl'] = round(unrealized_pnl, 2)
            trade['unrealized_pnl_percent'] = round(unrealized_pnl_percent, 2)

            # Check exit conditions
            close_reason = None

            if current_price <= trade['stop_loss_price']:
                close_reason = 'stop_loss'
            elif current_price >= trade['take_profit_price']:
                close_reason = 'take_profit'

            if close_reason:
                closed = self._close_trade(trade, current_price, close_reason)
                closed_trades.append(closed)
                self.portfolio.open_positions.remove(trade)

        return closed_trades

    def _close_trade(self, trade: Dict, exit_price: float, close_reason: str) -> Dict:
        """Close a trade and record results."""
        realized_pnl = (exit_price - trade['entry_price']) * trade['shares']
        realized_pnl_percent = (exit_price - trade['entry_price']) / trade['entry_price'] * 100

        closed_trade = trade.copy()
        closed_trade.update({
            'exit_date': datetime.now().isoformat(),
            'exit_price': round(exit_price, 2),
            'realized_pnl': round(realized_pnl, 2),
            'realized_pnl_percent': round(realized_pnl_percent, 2),
            'close_reason': close_reason,
            'status': 'closed'
        })

        self.portfolio.add_closed_position(closed_trade)
        logger.info(f"{trade['symbol']}: CLOSE {trade['shares']:.4f} @ ${exit_price} ({close_reason}, ${realized_pnl:.2f})")

        return closed_trade


class Portfolio:
    def __init__(self, config: dict, portfolio_file: str = 'data/portfolio.json'):
        self.config = config
        self.portfolio_file = portfolio_file
        self.starting_balance = config['trading']['starting_balance']
        self.cash = self.starting_balance
        self.open_positions = []
        self.closed_positions = []
        self.equity = self.starting_balance
        self.load_portfolio()

    def load_portfolio(self):
        """Load portfolio from file if exists."""
        try:
            with open(self.portfolio_file, 'r') as f:
                data = json.load(f)
                self.cash = data.get('cash', self.starting_balance)
                self.open_positions = data.get('open_positions', [])
                self.closed_positions = data.get('closed_positions', [])
                self.equity = self.calculate_equity()
                logger.info(f"Loaded portfolio: cash=${self.cash:.2f}, open={len(self.open_positions)}")
        except FileNotFoundError:
            logger.info(f"New portfolio created with ${self.starting_balance:.2f}")
        except Exception as e:
            logger.error(f"Failed to load portfolio: {str(e)}")

    def add_open_position(self, trade: Dict):
        """Add an open position."""
        self.open_positions.append(trade)
        self.cash -= trade['allocated_capital']
        self.equity = self.calculate_equity()
        self.save_portfolio()

    def add_closed_position(self, trade: Dict):
        """Add a closed position (realized trade)."""
        self.closed_positions.append(trade)
        self.cash += trade['allocated_capital'] + trade['realized_pnl']
        self.equity = self.calculate_equity()
        self.save_portfolio()

    def calculate_equity(self, unrealized_pnl: float = 0) -> float:
        """Calculate total equity including unrealized PnL."""
        unrealized = sum(t.get('unrealized_pnl', 0) for t in self.open_positions)
        return self.cash + unrealized + unrealized_pnl

    def get_cash(self) -> float:
        """Get available cash."""
        return self.cash

    @property
    def open_positions(self) -> List[Dict]:
        """Get open positions."""
        return self._open_positions

    @open_positions.setter
    def open_positions(self, value: List[Dict]):
        """Set open positions."""
        self._open_positions = value
        self.equity = self.calculate_equity()

    @property
    def total_pnl(self) -> float:
        """Calculate total P&L from closed trades."""
        return sum(t.get('realized_pnl', 0) for t in self.closed_positions)

    @property
    def win_count(self) -> int:
        """Count winning trades."""
        return sum(1 for t in self.closed_positions if t.get('realized_pnl', 0) > 0)

    @property
    def loss_count(self) -> int:
        """Count losing trades."""
        return sum(1 for t in self.closed_positions if t.get('realized_pnl', 0) < 0)

    @property
    def win_rate(self) -> float:
        """Calculate win rate."""
        total = len(self.closed_positions)
        if total == 0:
            return 0
        return self.win_count / total * 100

    def save_portfolio(self):
        """Save portfolio to file."""
        try:
            data = {
                'starting_balance': self.starting_balance,
                'cash': round(self.cash, 2),
                'equity': round(self.equity, 2),
                'open_positions': self.open_positions,
                'closed_positions': self.closed_positions,
                'total_pnl': round(self.total_pnl, 2),
                'win_rate': round(self.win_rate, 2),
                'trades_count': len(self.closed_positions),
                'last_updated': datetime.now().isoformat()
            }

            with open(self.portfolio_file, 'w') as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save portfolio: {str(e)}")

    def to_dict(self) -> Dict:
        """Export portfolio state as dict."""
        return {
            'starting_balance': self.starting_balance,
            'cash': round(self.cash, 2),
            'equity': round(self.equity, 2),
            'open_positions': len(self.open_positions),
            'closed_positions': len(self.closed_positions),
            'trades_count': len(self.closed_positions),
            'total_pnl': round(self.total_pnl, 2),
            'win_rate': round(self.win_rate, 2),
            'win_count': self.win_count,
            'loss_count': self.loss_count
        }
