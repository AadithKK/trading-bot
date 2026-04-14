import yfinance as yf
import pandas as pd
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json
import time

logger = logging.getLogger(__name__)

class MarketDataFetcher:
    def __init__(self, config: dict):
        self.config = config
        self.min_bars = config['thresholds']['min_bars_for_indicators']
        self.lookback_days = max(self.min_bars, 200)
        self.max_retries = 3
        self.retry_delay = 2

    def fetch_symbol(self, symbol: str) -> Optional[pd.DataFrame]:
        """Fetch OHLCV data for a symbol with retry logic."""
        for attempt in range(self.max_retries):
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(period='1y')

                if df.empty or len(df) < self.min_bars:
                    logger.warning(f"{symbol}: insufficient data ({len(df)} bars)")
                    return None

                if df['Close'].isnull().all():
                    logger.warning(f"{symbol}: all close prices are null")
                    return None

                df = df.dropna(subset=['Close', 'Volume'])
                if len(df) < self.min_bars:
                    logger.warning(f"{symbol}: not enough valid data after cleaning")
                    return None

                logger.debug(f"{symbol}: fetched {len(df)} bars")
                return df

            except Exception as e:
                if attempt < self.max_retries - 1:
                    logger.debug(f"{symbol}: attempt {attempt+1} failed, retrying in {self.retry_delay}s - {str(e)}")
                    time.sleep(self.retry_delay)
                else:
                    logger.error(f"{symbol}: data fetch failed after {self.max_retries} attempts - {str(e)}")
                    return None

    def fetch_multiple(self, symbols: List[str]) -> Dict[str, pd.DataFrame]:
        """Fetch data for multiple symbols, skip failures."""
        data = {}
        for symbol in symbols:
            df = self.fetch_symbol(symbol)
            if df is not None:
                data[symbol] = df

        logger.info(f"Fetched {len(data)}/{len(symbols)} symbols successfully")
        return data

    def get_current_price(self, df: pd.DataFrame) -> float:
        """Get the most recent close price."""
        return float(df['Close'].iloc[-1])

    def get_volume(self, df: pd.DataFrame) -> float:
        """Get the most recent volume."""
        return float(df['Volume'].iloc[-1])

    def get_avg_volume(self, df: pd.DataFrame, periods: int = 20) -> float:
        """Get average volume over last N periods."""
        return float(df['Volume'].tail(periods).mean())

    def get_price_history(self, df: pd.DataFrame, periods: int = 5) -> float:
        """Calculate total return over last N periods as percent."""
        if len(df) < periods + 1:
            return 0.0
        return float((df['Close'].iloc[-1] - df['Close'].iloc[-(periods+1)]) / df['Close'].iloc[-(periods+1)])

    def get_spy_data(self) -> Optional[pd.DataFrame]:
        """Fetch SPY benchmark data."""
        return self.fetch_symbol('SPY')


class WatchlistManager:
    def __init__(self, config: dict):
        self.config = config
        self.watchlist_file = 'data/watchlist.json'

    def build_watchlist(self, fetcher: MarketDataFetcher) -> List[str]:
        """Build watchlist from core symbols + dynamic sources."""
        symbols = set(self.config['watchlist']['core_symbols'].copy())

        if self.config['watchlist']['include_dynamic']:
            # For MVP, just use core symbols
            # Dynamic expansion (gainers, volume) can be added later
            pass

        symbols = list(symbols)
        self.save_watchlist(symbols)
        return symbols

    def save_watchlist(self, symbols: List[str]):
        """Save watchlist to JSON."""
        try:
            with open(self.watchlist_file, 'w') as f:
                json.dump({'symbols': symbols, 'timestamp': datetime.now().isoformat()}, f, indent=2)
            logger.info(f"Saved watchlist with {len(symbols)} symbols")
        except Exception as e:
            logger.error(f"Failed to save watchlist: {str(e)}")

    def load_watchlist(self) -> List[str]:
        """Load watchlist from JSON if exists."""
        try:
            with open(self.watchlist_file, 'r') as f:
                data = json.load(f)
                return data.get('symbols', [])
        except FileNotFoundError:
            return self.config['watchlist']['core_symbols'].copy()
        except Exception as e:
            logger.error(f"Failed to load watchlist: {str(e)}")
            return self.config['watchlist']['core_symbols'].copy()
