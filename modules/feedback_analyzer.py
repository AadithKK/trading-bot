"""
Feedback Analyzer Module
Reads trade history, calculates performance by signal condition segments,
and generates threshold adjustment suggestions. Only activates after
enough closed trades exist to make meaningful analysis.
"""

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

RSI_BUCKETS = [(25, 45), (45, 60), (60, 70), (70, 75)]


def load_closed_trades(csv_path: str):
    """
    Load only closed (non-open) trades from the trade log.
    Returns a pandas DataFrame or None if insufficient data.
    """
    try:
        import pandas as pd
        if not os.path.exists(csv_path):
            return None
        df = pd.read_csv(csv_path)
        closed = df[df["outcome"].isin(["win", "loss"])].copy()
        return closed if not closed.empty else None
    except Exception as exc:
        logger.warning(f"Could not load trade log: {exc}")
        return None


def calculate_win_rate(df) -> float:
    """Win rate as a fraction 0.0–1.0 from a closed-trades DataFrame."""
    if df is None or len(df) == 0:
        return 0.0
    wins = (df["outcome"] == "win").sum()
    return round(wins / len(df), 4)


def analyze_by_rsi_bucket(df) -> dict:
    """Win rate for each RSI bucket at entry."""
    results = {}
    try:
        import pandas as pd
        df = df.copy()
        df["rsi_at_entry"] = pd.to_numeric(df["rsi_at_entry"], errors="coerce")
        for low, high in RSI_BUCKETS:
            bucket = df[(df["rsi_at_entry"] >= low) & (df["rsi_at_entry"] < high)]
            label = f"{low}-{high}"
            results[label] = {
                "win_rate": calculate_win_rate(bucket),
                "trade_count": len(bucket),
            }
    except Exception as exc:
        logger.warning(f"RSI bucket analysis failed: {exc}")
    return results


def analyze_by_volatility(df) -> dict:
    """Win rate segmented by volatility level at entry."""
    results = {}
    try:
        for level in ["low", "medium", "high"]:
            subset = df[df["volatility"] == level]
            results[level] = {
                "win_rate": calculate_win_rate(subset),
                "trade_count": len(subset),
            }
    except Exception as exc:
        logger.warning(f"Volatility analysis failed: {exc}")
    return results


def analyze_by_trend(df) -> dict:
    """Win rate segmented by trend condition at entry."""
    results = {}
    try:
        for trend in ["uptrend", "downtrend", "sideways"]:
            subset = df[df["trend_at_entry"] == trend]
            results[trend] = {
                "win_rate": calculate_win_rate(subset),
                "trade_count": len(subset),
            }
    except Exception as exc:
        logger.warning(f"Trend analysis failed: {exc}")
    return results


def generate_suggestions(analysis: dict, config: dict) -> list[str]:
    """
    Compare segment win rates against the target and propose changes.
    Conservative: only narrows ranges, never widens.
    """
    suggestions = []
    target = config["feedback"]["win_rate_target"]
    step = config["feedback"]["rsi_adjustment_step"]
    thresh = config["signal_thresholds"]

    # RSI bucket analysis
    rsi_buckets = analysis.get("by_rsi_bucket", {})
    for label, data in rsi_buckets.items():
        if data["trade_count"] < 3:
            continue
        wr = data["win_rate"]
        if wr < target - 0.10:
            low, high = map(int, label.split("-"))
            if high == thresh["rsi_bullish_max"]:
                new_max = high - step
                suggestions.append(
                    f"RSI bullish max: reduce from {high} to {new_max} "
                    f"(bucket {label} win rate {wr:.0%} < target {target:.0%})"
                )
            if low == thresh["rsi_bullish_min"]:
                new_min = low + step
                suggestions.append(
                    f"RSI bullish min: increase from {low} to {new_min} "
                    f"(bucket {label} win rate {wr:.0%} < target {target:.0%})"
                )

    # Volatility analysis
    vol_data = analysis.get("by_volatility", {})
    high_vol = vol_data.get("high", {})
    if high_vol.get("trade_count", 0) >= 3 and high_vol.get("win_rate", 1.0) < target - 0.15:
        current_penalty = config["scoring_weights"]["high_volatility_penalty"]
        new_penalty = current_penalty - 5
        suggestions.append(
            f"High volatility penalty: increase from {current_penalty} to {new_penalty} "
            f"(high-vol win rate {high_vol['win_rate']:.0%})"
        )

    # Trend analysis
    trend_data = analysis.get("by_trend", {})
    for trend, data in trend_data.items():
        if data.get("trade_count", 0) >= 3 and data.get("win_rate", 1.0) < target - 0.15:
            suggestions.append(
                f"Trend '{trend}' underperforming: win rate {data['win_rate']:.0%}. "
                f"Consider reducing signal strength from {trend} trades."
            )

    return suggestions


def propose_config_changes(suggestions: list[str], config: dict) -> dict:
    """Build a proposed config diff based on the suggestions."""
    proposed = {}
    step = config["feedback"]["rsi_adjustment_step"]
    thresh = config["signal_thresholds"]

    for s in suggestions:
        if "RSI bullish max" in s and "reduce" in s:
            proposed["signal_thresholds.rsi_bullish_max"] = thresh["rsi_bullish_max"] - step
        if "RSI bullish min" in s and "increase" in s:
            proposed["signal_thresholds.rsi_bullish_min"] = thresh["rsi_bullish_min"] + step
        if "High volatility penalty" in s:
            proposed["scoring_weights.high_volatility_penalty"] = (
                config["scoring_weights"]["high_volatility_penalty"] - 5
            )

    return proposed


def write_feedback_report(report: dict, path: str) -> None:
    """Serialize the feedback report to JSON."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    logger.info(f"Feedback report written to {path}")


def apply_adjustments_to_config(proposed: dict, config: dict, config_path: str) -> None:
    """
    Apply proposed threshold changes to config.json.
    Only called when auto_apply_adjustments=true.
    """
    for key_path, value in proposed.items():
        parts = key_path.split(".")
        obj = config
        for part in parts[:-1]:
            obj = obj[part]
        old_value = obj[parts[-1]]
        obj[parts[-1]] = value
        logger.info(f"Config adjusted: {key_path} {old_value} → {value}")

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    logger.info("config.json updated with feedback adjustments")


def run_feedback_analysis(config: dict, paths: dict) -> dict | None:
    """
    Run the full feedback analysis cycle.
    Returns the report dict, or None if not enough closed trades exist.

    paths dict must include:
        "trade_log"     : path to trade_log.csv
        "feedback"      : path to feedback_report.json
        "config"        : path to config.json (for auto-apply)
    """
    min_trades = config["feedback"]["min_trades_for_analysis"]
    df = load_closed_trades(paths["trade_log"])

    if df is None or len(df) < min_trades:
        count = len(df) if df is not None else 0
        logger.info(
            f"Feedback skipped — only {count} closed trades "
            f"(need {min_trades})"
        )
        return None

    logger.info(f"Running feedback analysis on {len(df)} closed trades")

    analysis = {
        "by_rsi_bucket": analyze_by_rsi_bucket(df),
        "by_volatility": analyze_by_volatility(df),
        "by_trend": analyze_by_trend(df),
    }

    overall_win_rate = calculate_win_rate(df)
    suggestions = generate_suggestions(analysis, config)
    proposed = propose_config_changes(suggestions, config)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_closed_trades": len(df),
        "overall_win_rate": overall_win_rate,
        "win_rate_by_rsi_bucket": {
            k: v["win_rate"] for k, v in analysis["by_rsi_bucket"].items()
        },
        "win_rate_by_volatility": {
            k: v["win_rate"] for k, v in analysis["by_volatility"].items()
        },
        "win_rate_by_trend": {
            k: v["win_rate"] for k, v in analysis["by_trend"].items()
        },
        "suggestions": suggestions,
        "proposed_config_changes": proposed,
    }

    write_feedback_report(report, paths["feedback"])

    if config["feedback"]["auto_apply_adjustments"] and proposed:
        apply_adjustments_to_config(proposed, config, paths["config"])

    logger.info(
        f"Feedback complete — overall win rate: {overall_win_rate:.0%}, "
        f"{len(suggestions)} suggestion(s)"
    )
    return report
