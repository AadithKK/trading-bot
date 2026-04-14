#!/usr/bin/env python3
"""
Local Paper Trading Bot - Main Entry Point
Runs trading cycle: fetch data -> score signals -> AI review -> execute -> log results
"""

import json
import logging
import argparse
import sys
from datetime import datetime
from pathlib import Path

from modules.logger import setup_logging, TradeLogger
from modules.market_data import MarketDataFetcher, WatchlistManager
from modules.signal_engine import SignalEngine
from modules.ai_decision import OllamaAIDecider
from modules.execution import PaperExecutionEngine, Portfolio
from modules.github_sync import GitHubSync

logger = logging.getLogger(__name__)

class TradingBot:
    def __init__(self, config_file: str = 'config.json'):
        self.config = self.load_config(config_file)
        logger.info("=" * 60)
        logger.info("TRADING BOT STARTED")
        logger.info("=" * 60)

        self.portfolio = Portfolio(self.config)
        self.market_fetcher = MarketDataFetcher(self.config)
        self.watchlist_manager = WatchlistManager(self.config)
        self.signal_engine = SignalEngine(self.config)
        self.ai_decider = OllamaAIDecider(self.config)
        self.execution_engine = PaperExecutionEngine(self.config, self.portfolio)
        self.trade_logger = TradeLogger()
        self.github_sync = GitHubSync(self.config)

    def load_config(self, config_file: str) -> dict:
        """Load configuration from JSON."""
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {str(e)}")
            sys.exit(1)

    def run_cycle(self, force: bool = False) -> bool:
        """Run a complete trading cycle."""
        logger.info("Starting trading cycle...")

        # Check market hours (skip if not trading day)
        if not force and not self._is_trading_day():
            logger.info("Not a trading day, skipping cycle")
            return False

        run_stats = {
            'symbols_scanned': 0,
            'signals_generated': 0,
            'trades_opened': 0,
            'trades_closed': 0,
            'portfolio_equity': self.portfolio.equity,
            'ai_available': False
        }

        try:
            # Step 1: Load watchlist
            watchlist = self.watchlist_manager.load_watchlist()
            if not watchlist:
                watchlist = self.config['watchlist']['core_symbols']
                self.watchlist_manager.save_watchlist(watchlist)

            logger.info(f"Scanning {len(watchlist)} symbols...")
            run_stats['symbols_scanned'] = len(watchlist)

            # Step 2: Fetch market data
            market_data = self.market_fetcher.fetch_multiple(watchlist)
            spy_data = self.market_fetcher.get_spy_data()

            # Step 3: Score all symbols
            scores = self.signal_engine.score_all(market_data, spy_data)
            strong_signals = [s for s in scores if s.get('reject_reason') is None]
            logger.info(f"Generated {len(strong_signals)} valid signals")
            run_stats['signals_generated'] = len(strong_signals)

            # Step 4: Update existing positions
            current_prices = {
                symbol: self.market_fetcher.get_current_price(df)
                for symbol, df in market_data.items()
            }
            closed_trades = self.execution_engine.update_positions(current_prices)
            for trade in closed_trades:
                self.trade_logger.log_closed_trade(trade)
            logger.info(f"Closed {len(closed_trades)} positions")
            run_stats['trades_closed'] = len(closed_trades)

            # Step 5: Check AI availability
            ai_available = self.ai_decider.is_available()
            run_stats['ai_available'] = ai_available
            logger.info(f"Ollama AI: {'AVAILABLE' if ai_available else 'UNAVAILABLE'}")

            # Step 6: Get candidates for AI review
            candidates = self.signal_engine.filter_for_ai(strong_signals)
            auto_approve = self.signal_engine.get_auto_approve_trades(strong_signals)

            logger.info(f"AI review candidates: {len(candidates)}, Auto-approve: {len(auto_approve)}")

            # Step 7: Get AI decisions
            decisions = []

            # Auto-approve high-confidence trades
            for signal in auto_approve:
                decisions.append({
                    'symbol': signal['symbol'],
                    'action': 'BUY',
                    'confidence': min(100, signal['score']),
                    'position_size_percent': self.config['trading']['position_size_min_percent'],
                    'stop_loss_percent': self.config['trading']['stop_loss_percent'],
                    'take_profit_percent': self.config['trading']['take_profit_percent'],
                    'reasoning': 'auto_approved'
                })

            # Get AI decisions for borderline signals
            if candidates and ai_available:
                portfolio_state = {
                    'cash': self.portfolio.get_cash(),
                    'open_positions': len(self.portfolio.open_positions),
                    'max_positions': self.config['trading']['max_open_positions'],
                    'equity': self.portfolio.equity
                }
                ai_decisions = self.ai_decider.get_ai_decisions(candidates, portfolio_state)
                if ai_decisions:
                    decisions.extend(ai_decisions)

            logger.info(f"Total decisions: {len(decisions)}")

            # Step 8: Execute trades
            for decision in decisions:
                symbol = decision['symbol']
                if symbol in market_data:
                    current_price = current_prices[symbol]
                    trade = self.execution_engine.execute_trade(decision, current_price)
                    if trade:
                        run_stats['trades_opened'] += 1

            # Step 9: Save portfolio and log run
            self.portfolio.save_portfolio()
            run_stats['portfolio_equity'] = self.portfolio.equity
            self.trade_logger.log_run(run_stats)

            # Step 10: Update dashboard and sync to GitHub
            self.github_sync.update_dashboard(self.portfolio.to_dict())
            self.github_sync.commit_and_push(run_stats)

            logger.info(f"Cycle complete: Equity=${self.portfolio.equity:.2f}, "
                       f"Cash=${self.portfolio.get_cash():.2f}, "
                       f"Win rate: {self.portfolio.win_rate:.1f}%")

            return True

        except Exception as e:
            logger.error(f"Cycle failed: {str(e)}", exc_info=True)
            run_stats['status'] = 'failed'
            self.trade_logger.log_run(run_stats)
            return False

    def _is_trading_day(self) -> bool:
        """Check if today is a trading day."""
        import datetime as dt
        today = dt.datetime.now()

        # Skip weekends
        if today.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False

        # TODO: Add holiday checks

        return True

    def print_status(self):
        """Print current portfolio status."""
        logger.info("\n" + "=" * 60)
        logger.info("PORTFOLIO STATUS")
        logger.info("=" * 60)
        stats = self.portfolio.to_dict()
        for key, value in stats.items():
            logger.info(f"{key:.<40} {value}")
        logger.info("=" * 60 + "\n")

def main():
    parser = argparse.ArgumentParser(description='Local Paper Trading Bot')
    parser.add_argument('--config', default='config.json', help='Config file path')
    parser.add_argument('--force', action='store_true', help='Force run even outside market hours')
    parser.add_argument('--status', action='store_true', help='Print portfolio status and exit')
    args = parser.parse_args()

    # Setup logging
    config = json.load(open(args.config)) if Path(args.config).exists() else {}
    setup_logging(config)

    bot = TradingBot(args.config)

    if args.status:
        bot.print_status()
        return 0

    success = bot.run_cycle(force=args.force)
    return 0 if success else 1

if __name__ == '__main__':
    sys.exit(main())
