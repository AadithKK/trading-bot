import pandas as pd
import logging
from typing import Dict, List, Optional
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class SignalEngine:
    def __init__(self, config: dict):
        self.config = config
        self.signals_file = 'data/signals.json'

    def calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate RSI indicator."""
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50

    def calculate_sma(self, df: pd.DataFrame, period: int) -> float:
        """Calculate SMA."""
        sma = df['Close'].rolling(window=period).mean()
        return float(sma.iloc[-1]) if not pd.isna(sma.iloc[-1]) else 0

    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate ATR."""
        high = df['High']
        low = df['Low']
        close = df['Close']

        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        return float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else 0

    def get_trend_state(self, df: pd.DataFrame) -> str:
        """Determine if in uptrend, downtrend, or no trend."""
        price = df['Close'].iloc[-1]
        sma20 = self.calculate_sma(df, 20)
        sma50 = self.calculate_sma(df, 50)

        if price > sma20 > sma50:
            return 'uptrend'
        elif price < sma20 < sma50:
            return 'downtrend'
        else:
            return 'mixed'

    def calculate_momentum(self, df: pd.DataFrame, periods: int = 5) -> float:
        """Calculate 5-day momentum as percent change."""
        if len(df) < periods + 1:
            return 0.0
        return float((df['Close'].iloc[-1] - df['Close'].iloc[-(periods+1)]) / df['Close'].iloc[-(periods+1)])

    def calculate_relative_strength(self, df: pd.DataFrame, spy_df: pd.DataFrame) -> float:
        """Calculate stock performance vs SPY."""
        if spy_df is None or len(spy_df) < len(df):
            return 0.0

        stock_return = (df['Close'].iloc[-1] - df['Close'].iloc[0]) / df['Close'].iloc[0]
        spy_return = (spy_df['Close'].iloc[-1] - spy_df['Close'].iloc[0]) / spy_df['Close'].iloc[0]

        return float(stock_return - spy_return)

    def score_symbol(self, symbol: str, df: pd.DataFrame, spy_df: Optional[pd.DataFrame]) -> Dict:
        """Score a symbol on 0-100 scale."""
        try:
            current_price = df['Close'].iloc[-1]
            rsi = self.calculate_rsi(df)
            sma20 = self.calculate_sma(df, 20)
            sma50 = self.calculate_sma(df, 50)
            atr = self.calculate_atr(df)
            momentum = self.calculate_momentum(df)
            avg_volume = df['Volume'].tail(20).mean()
            current_volume = df['Volume'].iloc[-1]
            relative_strength = self.calculate_relative_strength(df, spy_df)
            trend_state = self.get_trend_state(df)

            score = 50
            notes = []
            reject_reason = None

            # Calculate volume and volatility metrics early (needed for all code paths)
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
            atr_percent = (atr / current_price) * 100 if current_price > 0 else 0

            # Trend alignment (uptrend needed for longs)
            if trend_state == 'uptrend':
                score += 30
                notes.append('uptrend')
            elif trend_state == 'downtrend':
                reject_reason = 'downtrend'
                score = 0
            else:
                notes.append('mixed_trend')

            if reject_reason is None:
                # RSI in range
                if self.config['signals']['rsi_valid_min'] <= rsi <= self.config['signals']['rsi_valid_max']:
                    score += 15
                    notes.append(f'rsi_good:{rsi:.0f}')
                elif rsi > self.config['signals']['rsi_avoid_above']:
                    reject_reason = f'rsi_overbought:{rsi:.0f}'
                    score -= 25
                elif rsi < self.config['signals']['rsi_avoid_below']:
                    reject_reason = f'rsi_oversold:{rsi:.0f}'
                    score -= 25

            if reject_reason is None:
                # Momentum
                if self.config['signals']['momentum_ideal_min'] <= momentum <= self.config['signals']['momentum_ideal_max']:
                    score += 15
                    notes.append(f'momentum_good:{momentum*100:.1f}%')
                elif momentum > self.config['signals']['momentum_avoid_above']:
                    reject_reason = f'momentum_extended:{momentum*100:.1f}%'
                    score -= 20
                elif momentum < self.config['signals']['momentum_avoid_below']:
                    notes.append(f'momentum_weak:{momentum*100:.1f}%')

            if reject_reason is None:
                # Volume
                if volume_ratio >= self.config['signals']['volume_ratio_threshold']:
                    score += 15
                    notes.append(f'volume_spike:{volume_ratio:.2f}x')
                else:
                    notes.append(f'volume_low:{volume_ratio:.2f}x')

                # Volatility
                if self.config['signals']['volatility_atr_min_percent'] <= atr_percent <= self.config['signals']['volatility_atr_max_percent']:
                    notes.append(f'volatility_ok:{atr_percent:.1f}%')
                elif atr_percent > self.config['signals']['volatility_atr_avoid_above']:
                    reject_reason = f'volatility_high:{atr_percent:.1f}%'
                    score -= 25

            if reject_reason is None:
                # Relative strength
                if relative_strength > 0:
                    score += 10
                    notes.append(f'outperforming_spy:{relative_strength*100:.1f}%')
                else:
                    notes.append(f'underperforming_spy:{relative_strength*100:.1f}%')

            score = max(0, min(100, score))

            return {
                'symbol': symbol,
                'score': score,
                'trend_state': trend_state,
                'rsi': round(rsi, 2),
                'momentum_percent': round(momentum * 100, 2),
                'volume_ratio': round(volume_ratio, 2),
                'atr_percent': round(atr_percent, 2),
                'relative_strength_percent': round(relative_strength * 100, 2),
                'notes': ', '.join(notes),
                'reject_reason': reject_reason,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"{symbol}: scoring failed - {str(e)}")
            return {
                'symbol': symbol,
                'score': 0,
                'reject_reason': f'error: {str(e)}',
                'timestamp': datetime.now().isoformat()
            }

    def score_all(self, data: Dict[str, pd.DataFrame], spy_df: Optional[pd.DataFrame]) -> List[Dict]:
        """Score all symbols, return sorted by score."""
        scores = []
        for symbol, df in data.items():
            score = self.score_symbol(symbol, df, spy_df)
            scores.append(score)

        scores.sort(key=lambda x: x['score'], reverse=True)
        self.save_signals(scores)
        return scores

    def save_signals(self, scores: List[Dict]):
        """Save signals to JSON."""
        try:
            with open(self.signals_file, 'w') as f:
                json.dump(scores, f, indent=2)
            logger.info(f"Saved {len(scores)} signals to {self.signals_file}")
        except Exception as e:
            logger.error(f"Failed to save signals: {str(e)}")

    def filter_for_ai(self, scores: List[Dict]) -> List[Dict]:
        """Filter signals suitable for AI review."""
        candidates = [
            s for s in scores
            if s.get('score', 0) >= self.config['signals']['min_score_for_ai'] and s.get('reject_reason') is None
        ]
        # Cap at AI review limit
        return candidates[:self.config['watchlist']['ai_review_cap']]

    def get_auto_approve_trades(self, scores: List[Dict]) -> List[Dict]:
        """Get signals that are strong enough to auto-approve (skip AI)."""
        return [
            s for s in scores
            if s.get('score', 0) >= self.config['signals']['auto_approve_score'] and s.get('reject_reason') is None
        ]
