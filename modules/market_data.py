"""
Market Data Module
Fetches OHLCV data from yfinance and computes all technical indicators
using pure pandas — no TA-Lib or C dependencies required.
"""

import logging
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_raw_data(symbol: str, period: str = "60d") -> pd.DataFrame | None:
    """Download daily OHLCV from yfinance. Returns None on failure."""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval="1d", auto_adjust=True)
        if df is None or df.empty or len(df) < 55:
            logger.warning(f"{symbol}: insufficient data ({len(df) if df is not None else 0} bars)")
            return None
        df.index = pd.to_datetime(df.index)
        return df
    except Exception as exc:
        logger.warning(f"{symbol}: fetch failed — {exc}")
        return None


def calculate_rsi(close: pd.Series, period: int = 14) -> float:
    """
    Wilder's RSI using EMA smoothing.
    Returns the most recent RSI value as a float rounded to 2 dp.
    """
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    latest = rsi.iloc[-1]
    return round(float(latest) if not math.isnan(latest) else 50.0, 2)


def classify_trend(df: pd.DataFrame, sma_short: int, sma_long: int) -> str:
    """
    Trend via SMA crossover.
    uptrend   : price > SMA_short > SMA_long
    downtrend : price < SMA_short < SMA_long
    sideways  : everything else
    """
    close = df["Close"]
    sma_s = close.rolling(sma_short).mean().iloc[-1]
    sma_l = close.rolling(sma_long).mean().iloc[-1]
    price = close.iloc[-1]

    if price > sma_s > sma_l:
        return "uptrend"
    if price < sma_s < sma_l:
        return "downtrend"
    return "sideways"


def detect_volume_spike(df: pd.DataFrame, window: int, multiplier: float) -> bool:
    """True if today's volume exceeds rolling-mean volume × multiplier."""
    volume = df["Volume"]
    rolling_mean = volume.rolling(window).mean().iloc[-1]
    current = volume.iloc[-1]
    if rolling_mean == 0 or math.isnan(rolling_mean):
        return False
    return bool(current > rolling_mean * multiplier)


def calculate_atr(df: pd.DataFrame, period: int) -> float:
    """Average True Range over `period` bars."""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr = tr.rolling(period).mean().iloc[-1]
    return float(atr) if not math.isnan(atr) else 0.0


def classify_volatility(
    df: pd.DataFrame,
    atr_period: int,
    high_thresh: float,
    low_thresh: float,
) -> str:
    """
    Normalized ATR (ATR / price).
    > high_thresh → "high", < low_thresh → "low", else "medium"
    """
    atr = calculate_atr(df, atr_period)
    price = df["Close"].iloc[-1]
    if price == 0:
        return "medium"
    norm_atr = atr / price
    if norm_atr >= high_thresh:
        return "high"
    if norm_atr <= low_thresh:
        return "low"
    return "medium"


def get_market_snapshot(symbol: str, config: dict) -> dict | None:
    """
    Fetch and normalize a single symbol into the standard snapshot format.
    Returns None if data is unavailable or insufficient.
    """
    thresh = config["signal_thresholds"]
    df = fetch_raw_data(symbol)
    if df is None:
        return None

    try:
        close = df["Close"]
        price = round(float(close.iloc[-1]), 4)
        rsi = calculate_rsi(close, thresh["rsi_period"])
        trend = classify_trend(df, thresh["trend_sma_short"], thresh["trend_sma_long"])
        volume_spike = detect_volume_spike(
            df, thresh["volume_rolling_window"], thresh["volume_spike_multiplier"]
        )
        volatility = classify_volatility(
            df,
            thresh["volatility_atr_period"],
            thresh["volatility_high_threshold"],
            thresh["volatility_low_threshold"],
        )
        sma_20 = round(float(close.rolling(thresh["trend_sma_short"]).mean().iloc[-1]), 4)
        sma_50 = round(float(close.rolling(thresh["trend_sma_long"]).mean().iloc[-1]), 4)

        return {
            "symbol": symbol,
            "price": price,
            "trend": trend,
            "rsi": rsi,
            "volatility": volatility,
            "volume_spike": volume_spike,
            "sma_20": sma_20,
            "sma_50": sma_50,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.warning(f"{symbol}: snapshot computation failed — {exc}")
        return None


def collect_all_symbols(config: dict) -> list[dict]:
    """
    Collect snapshots for every symbol in the watchlist.
    Skips symbols that return None and logs a warning.
    """
    snapshots = []
    for symbol in config["watchlist"]:
        snap = get_market_snapshot(symbol, config)
        if snap is not None:
            snapshots.append(snap)
            logger.info(
                f"{symbol}: price={snap['price']} rsi={snap['rsi']} "
                f"trend={snap['trend']} vol={snap['volatility']} "
                f"vol_spike={snap['volume_spike']}"
            )
        else:
            logger.warning(f"{symbol}: skipped (no data)")
    return snapshots
