"""
Price Alarm Manager
Manages price alerts for Solana memecoins.
Supports: price above/below, percentage change up/down.
"""

import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

ALARM_FILE = "alarms.json"


def load_alarms() -> dict:
    """Load all alarms from file."""
    try:
        if os.path.exists(ALARM_FILE):
            with open(ALARM_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Alarm load error: {e}")
    return {}


def save_alarms(data: dict):
    """Save all alarms to file."""
    try:
        with open(ALARM_FILE, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Alarm save error: {e}")


def add_price_alarm(user_id: int, token_address: str, token_name: str,
                    token_symbol: str, alarm_type: str, target_value: float,
                    current_price: float) -> dict:
    """
    Add a price alarm.
    alarm_type: 'price_above', 'price_below', 'pct_up', 'pct_down'
    """
    data = load_alarms()
    user_str = str(user_id)

    if user_str not in data:
        data[user_str] = []

    # Limit alarms per user (max 10)
    if len(data[user_str]) >= 10:
        return {"error": "Maximum 10 alarms allowed. Delete an existing alarm first."}

    alarm = {
        "id": len(data[user_str]) + 1,
        "token_address": token_address,
        "token_name": token_name,
        "token_symbol": token_symbol,
        "alarm_type": alarm_type,
        "target_value": target_value,
        "base_price": current_price,
        "created_at": datetime.now().isoformat(),
        "triggered": False,
        "active": True,
    }

    data[user_str].append(alarm)
    save_alarms(data)

    return {"success": True, "alarm": alarm}


def get_user_alarms(user_id: int) -> list:
    """Get all active alarms for a user."""
    data = load_alarms()
    user_str = str(user_id)
    alarms = data.get(user_str, [])
    return [a for a in alarms if a.get("active", True) and not a.get("triggered", False)]


def delete_alarm(user_id: int, alarm_id: int) -> bool:
    """Delete a specific alarm."""
    data = load_alarms()
    user_str = str(user_id)

    if user_str not in data:
        return False

    for alarm in data[user_str]:
        if alarm["id"] == alarm_id:
            alarm["active"] = False
            save_alarms(data)
            return True

    return False


def delete_all_alarms(user_id: int) -> int:
    """Delete all alarms for a user. Returns count deleted."""
    data = load_alarms()
    user_str = str(user_id)

    if user_str not in data:
        return 0

    count = len([a for a in data[user_str] if a.get("active", True)])
    for alarm in data[user_str]:
        alarm["active"] = False
    save_alarms(data)
    return count


def check_alarms(current_prices: dict) -> list:
    """
    Check all active alarms against current prices.
    current_prices: {token_address: {"price": float, "change_24h": float}}
    Returns list of triggered alarms: [{"user_id": int, "alarm": dict, "current_price": float}]
    """
    data = load_alarms()
    triggered = []

    for user_str, alarms in data.items():
        if user_str.startswith("__"):
            continue

        for alarm in alarms:
            if not alarm.get("active", True) or alarm.get("triggered", False):
                continue

            token_addr = alarm["token_address"]
            if token_addr not in current_prices:
                continue

            current_price = current_prices[token_addr]["price"]
            alarm_type = alarm["alarm_type"]
            target = alarm["target_value"]
            base_price = alarm.get("base_price", 0)

            should_trigger = False

            if alarm_type == "price_above" and current_price >= target:
                should_trigger = True
            elif alarm_type == "price_below" and current_price <= target:
                should_trigger = True
            elif alarm_type == "pct_up" and base_price > 0:
                pct_change = ((current_price - base_price) / base_price) * 100
                if pct_change >= target:
                    should_trigger = True
            elif alarm_type == "pct_down" and base_price > 0:
                pct_change = ((base_price - current_price) / base_price) * 100
                if pct_change >= target:
                    should_trigger = True

            if should_trigger:
                alarm["triggered"] = True
                triggered.append({
                    "user_id": int(user_str),
                    "alarm": alarm,
                    "current_price": current_price,
                })

    if triggered:
        save_alarms(data)

    return triggered


def get_all_watched_tokens() -> set:
    """Get all unique token addresses being watched by alarms."""
    data = load_alarms()
    tokens = set()

    for user_str, alarms in data.items():
        if user_str.startswith("__"):
            continue
        for alarm in alarms:
            if alarm.get("active", True) and not alarm.get("triggered", False):
                tokens.add(alarm["token_address"])

    return tokens


def format_alarm_text(alarm: dict) -> str:
    """Format a single alarm for display."""
    atype = alarm["alarm_type"]
    target = alarm["target_value"]
    symbol = alarm["token_symbol"]

    if atype == "price_above":
        desc = f"Price above ${target:,.6f}"
        icon = "📈"
    elif atype == "price_below":
        desc = f"Price below ${target:,.6f}"
        icon = "📉"
    elif atype == "pct_up":
        desc = f"Price up {target}%"
        icon = "🟢"
    elif atype == "pct_down":
        desc = f"Price down {target}%"
        icon = "🔴"
    else:
        desc = "Unknown"
        icon = "❓"

    return f"{icon} ${symbol} — {desc}"
