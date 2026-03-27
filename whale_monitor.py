"""
Whale Monitor
Tracks whale (large wallet) buy/sell activity for Solana memecoins.
Uses DexScreener API to detect large transactions.
"""

import json
import os
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

WHALE_FILE = "whale_alerts.json"


def load_whale_data() -> dict:
    """Load whale alert subscriptions."""
    try:
        if os.path.exists(WHALE_FILE):
            with open(WHALE_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Whale data load error: {e}")
    return {}


def save_whale_data(data: dict):
    """Save whale alert subscriptions."""
    try:
        with open(WHALE_FILE, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Whale data save error: {e}")


def add_whale_alert(user_id: int, token_address: str, token_name: str,
                    token_symbol: str) -> dict:
    """Add a whale tracking alert for a token."""
    data = load_whale_data()
    user_str = str(user_id)

    if user_str not in data:
        data[user_str] = []

    # Limit whale alerts per user (max 5)
    active_alerts = [a for a in data[user_str] if a.get("active", True)]
    if len(active_alerts) >= 5:
        return {"error": "Maximum 5 whale alerts allowed. Delete an existing alert first."}

    # Check if already tracking this token
    for alert in data[user_str]:
        if alert["token_address"] == token_address and alert.get("active", True):
            return {"error": f"Already tracking whale activity for ${token_symbol}."}

    alert = {
        "id": len(data[user_str]) + 1,
        "token_address": token_address,
        "token_name": token_name,
        "token_symbol": token_symbol,
        "created_at": datetime.now().isoformat(),
        "active": True,
        "last_check": None,
        "last_known_buys": None,
        "last_known_sells": None,
    }

    data[user_str].append(alert)
    save_whale_data(data)

    return {"success": True, "alert": alert}


def get_user_whale_alerts(user_id: int) -> list:
    """Get all active whale alerts for a user."""
    data = load_whale_data()
    user_str = str(user_id)
    alerts = data.get(user_str, [])
    return [a for a in alerts if a.get("active", True)]


def delete_whale_alert(user_id: int, alert_id: int) -> bool:
    """Delete a specific whale alert."""
    data = load_whale_data()
    user_str = str(user_id)

    if user_str not in data:
        return False

    for alert in data[user_str]:
        if alert["id"] == alert_id:
            alert["active"] = False
            save_whale_data(data)
            return True

    return False


def delete_all_whale_alerts(user_id: int) -> int:
    """Delete all whale alerts for a user. Returns count deleted."""
    data = load_whale_data()
    user_str = str(user_id)

    if user_str not in data:
        return 0

    count = len([a for a in data[user_str] if a.get("active", True)])
    for alert in data[user_str]:
        alert["active"] = False
    save_whale_data(data)
    return count


def get_all_whale_tokens() -> dict:
    """
    Get all unique token addresses being watched for whales.
    Returns: {token_address: [user_ids]}
    """
    data = load_whale_data()
    tokens = {}

    for user_str, alerts in data.items():
        if user_str.startswith("__"):
            continue
        for alert in alerts:
            if alert.get("active", True):
                addr = alert["token_address"]
                if addr not in tokens:
                    tokens[addr] = []
                tokens[addr].append(int(user_str))

    return tokens


def check_whale_activity(token_address: str) -> dict:
    """
    Check for whale activity on a token using DexScreener data.
    Detects significant changes in buy/sell transaction counts and volume.
    """
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()

        if not data.get("pairs") or len(data["pairs"]) == 0:
            return {"error": "Token not found"}

        # Get best pair by liquidity
        pairs = data["pairs"]
        best_pair = max(pairs, key=lambda x: float(x.get("liquidity", {}).get("usd", 0) or 0))

        txns_1h = best_pair.get("txns", {}).get("h1", {})
        txns_5m = best_pair.get("txns", {}).get("m5", {})
        volume_1h = float(best_pair.get("volume", {}).get("h1", 0) or 0)
        volume_5m = float(best_pair.get("volume", {}).get("m5", 0) or 0)
        liquidity = float(best_pair.get("liquidity", {}).get("usd", 0) or 0)
        price_change_5m = float(best_pair.get("priceChange", {}).get("m5", 0) or 0)
        price_change_1h = float(best_pair.get("priceChange", {}).get("h1", 0) or 0)
        price_usd = best_pair.get("priceUsd", "0")
        name = best_pair.get("baseToken", {}).get("name", "Unknown")
        symbol = best_pair.get("baseToken", {}).get("symbol", "???")

        buys_1h = int(txns_1h.get("buys", 0) or 0)
        sells_1h = int(txns_1h.get("sells", 0) or 0)
        buys_5m = int(txns_5m.get("buys", 0) or 0)
        sells_5m = int(txns_5m.get("sells", 0) or 0)

        # Detect whale activity indicators
        whale_signals = []

        # Large volume spike relative to liquidity (>20% of pool in 1h)
        if liquidity > 0 and volume_1h > liquidity * 0.2:
            vol_ratio = volume_1h / liquidity
            whale_signals.append({
                "type": "volume_spike",
                "direction": "neutral",
                "detail": f"Volume spike detected: ${volume_1h:,.0f} in 1h ({vol_ratio:.1f}x liquidity)",
            })

        # Sharp price movement in 5 minutes
        if abs(price_change_5m) > 10:
            direction = "buy" if price_change_5m > 0 else "sell"
            whale_signals.append({
                "type": "price_spike",
                "direction": direction,
                "detail": f"Sharp {direction} pressure: {price_change_5m:+.1f}% in 5 min",
            })

        # Large buy/sell imbalance in 5 minutes
        total_5m = buys_5m + sells_5m
        if total_5m > 5:
            if buys_5m > sells_5m * 3:
                whale_signals.append({
                    "type": "buy_surge",
                    "direction": "buy",
                    "detail": f"Whale buying detected: {buys_5m} buys vs {sells_5m} sells in 5 min",
                })
            elif sells_5m > buys_5m * 3:
                whale_signals.append({
                    "type": "sell_surge",
                    "direction": "sell",
                    "detail": f"Whale selling detected: {sells_5m} sells vs {buys_5m} buys in 5 min",
                })

        # High volume per transaction (whale-sized trades)
        if total_5m > 0 and volume_5m > 0:
            avg_trade = volume_5m / total_5m
            if avg_trade > 5000:
                whale_signals.append({
                    "type": "large_trades",
                    "direction": "neutral",
                    "detail": f"Large avg trade size: ${avg_trade:,.0f} per transaction",
                })

        return {
            "token_address": token_address,
            "name": name,
            "symbol": symbol,
            "price": price_usd,
            "price_change_5m": price_change_5m,
            "price_change_1h": price_change_1h,
            "volume_1h": volume_1h,
            "buys_1h": buys_1h,
            "sells_1h": sells_1h,
            "buys_5m": buys_5m,
            "sells_5m": sells_5m,
            "liquidity": liquidity,
            "whale_signals": whale_signals,
            "has_activity": len(whale_signals) > 0,
        }

    except Exception as e:
        logger.error(f"Whale check error for {token_address}: {e}")
        return {"error": str(e)}


def format_whale_alert_text(alert_data: dict, token_symbol: str) -> str:
    """Format whale activity notification text."""
    signals = alert_data.get("whale_signals", [])
    if not signals:
        return ""

    price = alert_data.get("price", "0")
    change_5m = alert_data.get("price_change_5m", 0)
    change_1h = alert_data.get("price_change_1h", 0)

    text = (
        f"🐋 WHALE ALERT — ${token_symbol}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 Price: ${price}\n"
        f"⏱ 5m: {change_5m:+.1f}% | 1h: {change_1h:+.1f}%\n\n"
    )

    for signal in signals:
        direction = signal["direction"]
        if direction == "buy":
            icon = "🟢"
        elif direction == "sell":
            icon = "🔴"
        else:
            icon = "⚡"
        text += f"{icon} {signal['detail']}\n"

    text += f"\n🕐 {datetime.now().strftime('%H:%M:%S')}"
    return text
