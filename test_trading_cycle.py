#!/usr/bin/env python3
"""
Test script to verify the trading bot works end-to-end with simulated data.
This bypasses yfinance and tests the core trading logic.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
import pandas as pd
import numpy as np

# Create synthetic OHLCV data for testing
def create_test_data(symbol: str, num_bars: int = 200) -> pd.DataFrame:
    """Create realistic synthetic OHLCV data."""
    np.random.seed(hash(symbol) % 2**32)
    dates = pd.date_range(end=datetime.now(), periods=num_bars, freq='1D')

    # Generate price data with trend
    base_price = 100
    returns = np.random.normal(0.001, 0.02, num_bars)
    prices = base_price * np.cumprod(1 + returns)

    df = pd.DataFrame({
        'Open': prices * (1 + np.random.uniform(-0.005, 0.005, num_bars)),
        'High': prices * (1 + np.random.uniform(0, 0.01, num_bars)),
        'Low': prices * (1 - np.random.uniform(0, 0.01, num_bars)),
        'Close': prices,
        'Volume': np.random.randint(1000000, 10000000, num_bars),
    }, index=dates)

    return df

# Test the core trading logic
def test_trading_cycle():
    """Run a trading cycle with test data."""
    from modules.signal_engine import SignalEngine
    from modules.execution import PaperExecutionEngine, Portfolio
    from modules.ai_decision import OllamaAIDecider
    from modules.logger import TradeLogger

    # Load config
    with open('config.json', 'r') as f:
        config = json.load(f)

    print("\n" + "="*60)
    print("TEST TRADING CYCLE WITH SIMULATED DATA")
    print("="*60)

    # Initialize components
    portfolio = Portfolio(config)
    signal_engine = SignalEngine(config)
    ai_decider = OllamaAIDecider(config)
    execution_engine = PaperExecutionEngine(config, portfolio)
    trade_logger = TradeLogger()

    # Create test data
    test_symbols = ['AAPL', 'MSFT', 'NVDA', 'TSLA']
    market_data = {}
    spy_data = None

    print(f"\nGenerating synthetic data for {len(test_symbols)} symbols...")
    for symbol in test_symbols:
        market_data[symbol] = create_test_data(symbol)
        if symbol == 'AAPL':
            spy_data = create_test_data('SPY')  # Use AAPL data as SPY proxy

    print(f"[OK] Generated {len(market_data)} symbols with 200 bars each")

    # Score all symbols
    print("\nScoring signals...")
    scores = signal_engine.score_all(market_data, spy_data)
    strong_signals = [s for s in scores if s.get('reject_reason') is None]
    print(f"[OK] Generated {len(strong_signals)} valid signals from {len(scores)} total")

    # Get current prices
    current_prices = {
        symbol: market_data[symbol]['Close'].iloc[-1]
        for symbol in market_data.keys()
    }

    # Get trade candidates and auto-approve
    candidates = signal_engine.filter_for_ai(strong_signals)
    auto_approve = signal_engine.get_auto_approve_trades(strong_signals)

    print(f"\nAI review candidates: {len(candidates)}, Auto-approve: {len(auto_approve)}")

    # Build decisions
    decisions = []
    for signal in auto_approve:
        decisions.append({
            'symbol': signal['symbol'],
            'action': 'BUY',
            'confidence': min(100, signal['score']),
            'position_size_percent': config['trading']['position_size_min_percent'],
            'stop_loss_percent': config['trading']['stop_loss_percent'],
            'take_profit_percent': config['trading']['take_profit_percent'],
            'reasoning': 'test_auto_approve'
        })

    # Execute trades
    print(f"\nExecuting {len(decisions)} trades...")
    trades_opened = 0
    for decision in decisions:
        symbol = decision['symbol']
        if symbol in current_prices:
            trade = execution_engine.execute_trade(decision, current_prices[symbol])
            if trade:
                trades_opened += 1
                print(f"  [OK] {symbol}: {trade['shares']:.4f} shares @ ${trade['entry_price']}")

    # Simulate price movement and close some trades
    print(f"\nSimulating price movements...")
    new_prices = {}
    for symbol in market_data:
        # Simulate ±5% price movement
        price_change = np.random.uniform(-0.05, 0.05)
        new_prices[symbol] = current_prices[symbol] * (1 + price_change)

    closed_trades = execution_engine.update_positions(new_prices)
    print(f"[OK] Closed {len(closed_trades)} positions")
    for trade in closed_trades:
        print(f"  [OK] {trade['symbol']}: {trade['realized_pnl']:.2f} PnL ({trade['close_reason']})")

    # Save and verify
    print(f"\nSaving portfolio state...")
    portfolio.save_portfolio()

    # Verify data
    print("\n" + "="*60)
    print("VERIFICATION")
    print("="*60)

    portfolio_data = portfolio.to_dict()
    for key, value in portfolio_data.items():
        print(f"{key:.<40} {value}")

    # Check files exist
    print("\n" + "="*60)
    print("FILE CREATION CHECK")
    print("="*60)

    files_to_check = [
        'data/portfolio.json',
        'data/signals.json',
        'data/trade_log.csv',
        'data/runs.json',
        'logs/system.log'
    ]

    for file in files_to_check:
        exists = Path(file).exists()
        size = Path(file).stat().st_size if exists else 0
        status = "[OK]" if exists else "[FAIL]"
        print(f"{status} {file:.<40} ({size} bytes)")

    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60 + "\n")

    return True

if __name__ == '__main__':
    try:
        success = test_trading_cycle()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n[FAIL] Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
