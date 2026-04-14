"""
Signal Engine Module
Fully deterministic, rule-based signal scoring. No AI, no randomness.
All thresholds sourced from config so the feedback loop can tune them.
"""

import logging

logger = logging.getLogger(__name__)


def classify_signal_direction(snapshot: dict, config: dict) -> str:
    """
    Determine raw signal direction from snapshot indicators.
    Returns "bullish", "bearish", or "neutral".
    """
    thresh = config["signal_thresholds"]
    trend = snapshot["trend"]
    rsi = snapshot["rsi"]
    volatility = snapshot["volatility"]
    volume_spike = snapshot["volume_spike"]

    rsi_bull_min = thresh["rsi_bullish_min"]
    rsi_bull_max = thresh["rsi_bullish_max"]
    rsi_bear_max = thresh["rsi_bearish_max"]
    rsi_overbought = thresh["rsi_overbought"]
    rsi_oversold = thresh["rsi_oversold"]

    # Force neutral on RSI extremes (overbought/oversold)
    if rsi > rsi_overbought or rsi < rsi_oversold:
        return "neutral"

    # High volatility with no clear trend → neutral
    if volatility == "high" and trend == "sideways":
        return "neutral"

    # Bullish: uptrend + RSI in bullish range
    if trend == "uptrend" and rsi_bull_min <= rsi <= rsi_bull_max:
        if volume_spike or rsi >= rsi_bull_min:
            return "bullish"

    # Bearish: downtrend + RSI below bearish threshold
    if trend == "downtrend" and rsi <= rsi_bear_max:
        return "bearish"

    return "neutral"


def _detect_mixed_signals(snapshot: dict, direction: str, config: dict) -> bool:
    """
    True if contradictory indicators are present simultaneously.
    Examples: uptrend but RSI already in bearish zone; volume spike but high volatility.
    """
    thresh = config["signal_thresholds"]
    trend = snapshot["trend"]
    rsi = snapshot["rsi"]
    volatility = snapshot["volatility"]
    volume_spike = snapshot["volume_spike"]

    # Uptrend but RSI is in a bearish-leaning region
    if trend == "uptrend" and rsi < thresh["rsi_bullish_min"]:
        return True
    # Downtrend but RSI is in a bullish-leaning region
    if trend == "downtrend" and rsi > thresh["rsi_bullish_max"]:
        return True
    # Volume spike accompanied by high volatility — unreliable signal
    if volume_spike and volatility == "high":
        return True
    # Signal direction conflicts with trend
    if direction == "bullish" and trend == "downtrend":
        return True
    if direction == "bearish" and trend == "uptrend":
        return True

    return False


def score_signal(snapshot: dict, config: dict) -> dict:
    """
    Score a single snapshot and return {symbol, signal, strength}.
    Strength is clamped to [0, 100].
    """
    weights = config["scoring_weights"]
    thresh = config["signal_thresholds"]

    direction = classify_signal_direction(snapshot, config)
    trend = snapshot["trend"]
    rsi = snapshot["rsi"]
    volatility = snapshot["volatility"]
    volume_spike = snapshot["volume_spike"]

    score = weights["base"]  # 50

    # Trend alignment bonus
    if (direction == "bullish" and trend == "uptrend") or \
       (direction == "bearish" and trend == "downtrend"):
        score += weights["trend_alignment"]  # +30

    # RSI alignment bonus
    rsi_bull_min = thresh["rsi_bullish_min"]
    rsi_bull_max = thresh["rsi_bullish_max"]
    rsi_bear_max = thresh["rsi_bearish_max"]

    if direction == "bullish" and rsi_bull_min <= rsi <= rsi_bull_max:
        score += weights["rsi_alignment"]  # +15
    elif direction == "bearish" and rsi <= rsi_bear_max:
        score += weights["rsi_alignment"]  # +15

    # Volume confirmation bonus
    if volume_spike:
        score += weights["volume_confirmation"]  # +15

    # High volatility penalty
    if volatility == "high":
        score += weights["high_volatility_penalty"]  # -25

    # Mixed signals penalty
    if _detect_mixed_signals(snapshot, direction, config):
        score += weights["mixed_signals_penalty"]  # -20

    # Clamp
    score = max(0, min(100, score))

    # Override: RSI extremes force low-strength neutral
    if rsi > thresh["rsi_overbought"] or rsi < thresh["rsi_oversold"]:
        direction = "neutral"
        score = min(score, 40)

    result = {
        "symbol": snapshot["symbol"],
        "signal": direction,
        "strength": score,
    }
    logger.debug(
        f"{snapshot['symbol']}: direction={direction} strength={score} "
        f"(trend={snapshot['trend']} rsi={rsi} vol={volatility} spike={volume_spike})"
    )
    return result


def generate_signals(snapshots: list[dict], config: dict) -> list[dict]:
    """Score all snapshots and return the full signals list."""
    signals = []
    for snap in snapshots:
        sig = score_signal(snap, config)
        signals.append(sig)
        logger.info(f"{sig['symbol']}: signal={sig['signal']} strength={sig['strength']}")
    return signals


def filter_by_min_strength(signals: list[dict], min_strength: int) -> list[dict]:
    """Keep only signals at or above the minimum strength threshold."""
    filtered = [s for s in signals if s["strength"] >= min_strength]
    logger.info(
        f"Signal filter: {len(filtered)}/{len(signals)} symbols passed "
        f"(min_strength={min_strength})"
    )
    return filtered
