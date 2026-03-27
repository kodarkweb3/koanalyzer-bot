"""
Auto-Sniper Alerts for kodark.io Bot
Monitors new token launches on Solana DEXes (Pump.fun, Raydium, Jupiter).
Notifies subscribed users when promising new tokens appear.
"""

import json
import logging
import requests
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

SNIPER_FILE = "sniper_alerts.json"

# ==================== DATA PERSISTENCE ====================

def load_sniper_data() -> dict:
    """Load sniper alert subscriptions from file."""
    try:
        with open(SNIPER_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"subscriptions": {}, "seen_tokens": [], "last_check": None}


def save_sniper_data(data: dict):
    """Save sniper alert subscriptions to file."""
    try:
        with open(SNIPER_FILE, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error saving sniper data: {e}")


# ==================== SUBSCRIPTION MANAGEMENT ====================

PLATFORM_OPTIONS = {
    "all": "🌐 All Platforms",
    "pump_fun": "🎰 Pump.fun",
    "raydium": "💧 Raydium",
    "jupiter": "🪐 Jupiter",
}


def subscribe_sniper(user_id: int, platform: str = "all") -> dict:
    """Subscribe a user to sniper alerts for a platform."""
    data = load_sniper_data()
    uid = str(user_id)

    if uid not in data["subscriptions"]:
        data["subscriptions"][uid] = {
            "platforms": [],
            "created_at": datetime.now().isoformat(),
            "active": True,
            "min_liquidity": 1000,  # Minimum $1k liquidity
            "min_volume": 500,      # Minimum $500 volume
        }

    sub = data["subscriptions"][uid]

    if platform == "all":
        sub["platforms"] = ["pump_fun", "raydium", "jupiter"]
    elif platform not in sub["platforms"]:
        sub["platforms"].append(platform)

    sub["active"] = True
    save_sniper_data(data)

    return {"success": True, "platforms": sub["platforms"]}


def unsubscribe_sniper(user_id: int, platform: str = "all") -> dict:
    """Unsubscribe a user from sniper alerts."""
    data = load_sniper_data()
    uid = str(user_id)

    if uid not in data["subscriptions"]:
        return {"success": False, "message": "No active subscription found."}

    sub = data["subscriptions"][uid]

    if platform == "all":
        sub["platforms"] = []
        sub["active"] = False
    elif platform in sub["platforms"]:
        sub["platforms"].remove(platform)
        if not sub["platforms"]:
            sub["active"] = False

    save_sniper_data(data)
    return {"success": True, "platforms": sub["platforms"]}


def get_user_sniper_status(user_id: int) -> dict:
    """Get a user's sniper alert subscription status."""
    data = load_sniper_data()
    uid = str(user_id)

    if uid not in data["subscriptions"]:
        return {"active": False, "platforms": []}

    sub = data["subscriptions"][uid]
    return {
        "active": sub.get("active", False),
        "platforms": sub.get("platforms", []),
        "created_at": sub.get("created_at", ""),
        "min_liquidity": sub.get("min_liquidity", 1000),
        "min_volume": sub.get("min_volume", 500),
    }


def get_all_sniper_subscribers() -> dict:
    """Get all active sniper subscribers grouped by platform."""
    data = load_sniper_data()
    platform_users = {
        "pump_fun": [],
        "raydium": [],
        "jupiter": [],
    }

    for uid, sub in data["subscriptions"].items():
        if not sub.get("active", False):
            continue
        for platform in sub.get("platforms", []):
            if platform in platform_users:
                platform_users[platform].append(int(uid))

    return platform_users


# ==================== NEW TOKEN DETECTION ====================

# DEX ID mapping for DexScreener
DEX_PLATFORM_MAP = {
    "pump_fun": ["pump", "pumpfun", "pump.fun"],
    "raydium": ["raydium"],
    "jupiter": ["jupiter", "meteora"],
}


def check_new_tokens() -> list:
    """
    Check for new Solana token launches using DexScreener API.
    Returns list of new tokens with their data.
    """
    data = load_sniper_data()
    seen = set(data.get("seen_tokens", []))
    new_tokens = []

    try:
        # Fetch latest Solana pairs from DexScreener
        url = "https://api.dexscreener.com/latest/dex/pairs/solana"
        # Also check token boosts for trending new tokens
        boost_url = "https://api.dexscreener.com/token-boosts/latest/v1"

        # Method 1: Latest boosted tokens (often new launches)
        try:
            resp = requests.get(boost_url, timeout=15)
            resp.raise_for_status()
            boost_data = resp.json()

            for token in boost_data:
                if token.get("chainId") != "solana":
                    continue

                addr = token.get("tokenAddress", "")
                if not addr or addr in seen:
                    continue

                # Get full token data
                token_info = _get_token_quick_info(addr)
                if token_info and _passes_filters(token_info, data):
                    token_info["source"] = "boost"
                    new_tokens.append(token_info)
                    seen.add(addr)

        except Exception as e:
            logger.error(f"Boost check error: {e}")

        # Method 2: Check DexScreener trending for new Solana tokens
        try:
            trend_url = "https://api.dexscreener.com/token-profiles/latest/v1"
            resp = requests.get(trend_url, timeout=15)
            resp.raise_for_status()
            trend_data = resp.json()

            for token in trend_data:
                if token.get("chainId") != "solana":
                    continue

                addr = token.get("tokenAddress", "")
                if not addr or addr in seen:
                    continue

                token_info = _get_token_quick_info(addr)
                if token_info and _passes_filters(token_info, data):
                    token_info["source"] = "profile"
                    new_tokens.append(token_info)
                    seen.add(addr)

        except Exception as e:
            logger.error(f"Profile check error: {e}")

        # Keep seen list manageable (last 500 tokens)
        seen_list = list(seen)
        if len(seen_list) > 500:
            seen_list = seen_list[-500:]

        data["seen_tokens"] = seen_list
        data["last_check"] = datetime.now().isoformat()
        save_sniper_data(data)

    except Exception as e:
        logger.error(f"New token check error: {e}")

    return new_tokens[:10]  # Max 10 per check cycle


def _get_token_quick_info(token_address: str) -> dict:
    """Get quick token info for sniper alert."""
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if not data.get("pairs"):
            return None

        pairs = data["pairs"]
        best = max(pairs, key=lambda x: float(x.get("liquidity", {}).get("usd", 0) or 0))

        liquidity = float(best.get("liquidity", {}).get("usd", 0) or 0)
        volume_24h = float(best.get("volume", {}).get("h24", 0) or 0)
        volume_1h = float(best.get("volume", {}).get("h1", 0) or 0)
        mcap = float(best.get("marketCap", 0) or best.get("fdv", 0) or 0)
        price = best.get("priceUsd", "0")
        change_5m = float(best.get("priceChange", {}).get("m5", 0) or 0)
        change_1h = float(best.get("priceChange", {}).get("h1", 0) or 0)
        change_24h = float(best.get("priceChange", {}).get("h24", 0) or 0)
        buys_1h = int(best.get("txns", {}).get("h1", {}).get("buys", 0) or 0)
        sells_1h = int(best.get("txns", {}).get("h1", {}).get("sells", 0) or 0)
        dex_id = best.get("dexId", "").lower()

        # Calculate age
        age_str = "Unknown"
        is_new = False
        created_at = best.get("pairCreatedAt")
        if created_at:
            try:
                created = datetime.fromtimestamp(created_at / 1000)
                age = datetime.now() - created
                if age.days == 0:
                    if age.seconds < 3600:
                        age_str = f"{age.seconds // 60}m"
                        is_new = True
                    else:
                        age_str = f"{age.seconds // 3600}h"
                        is_new = age.seconds < 86400  # Less than 24h
                elif age.days < 3:
                    age_str = f"{age.days}d {age.seconds // 3600}h"
                    is_new = True
                else:
                    age_str = f"{age.days}d"
            except:
                pass

        # Determine platform
        platform = "unknown"
        for plat, dex_ids in DEX_PLATFORM_MAP.items():
            if any(d in dex_id for d in dex_ids):
                platform = plat
                break

        return {
            "address": token_address,
            "name": best.get("baseToken", {}).get("name", "Unknown"),
            "symbol": best.get("baseToken", {}).get("symbol", "???"),
            "price": price,
            "market_cap": mcap,
            "liquidity": liquidity,
            "volume_24h": volume_24h,
            "volume_1h": volume_1h,
            "change_5m": change_5m,
            "change_1h": change_1h,
            "change_24h": change_24h,
            "buys_1h": buys_1h,
            "sells_1h": sells_1h,
            "dex_id": dex_id,
            "platform": platform,
            "age": age_str,
            "is_new": is_new,
            "url": best.get("url", ""),
            "total_pairs": len(pairs),
        }

    except Exception as e:
        logger.debug(f"Quick info error for {token_address}: {e}")
        return None


def _passes_filters(token_info: dict, sniper_data: dict) -> bool:
    """Check if a token passes the minimum filters for sniper alerts."""
    # Must have some liquidity
    if token_info.get("liquidity", 0) < 500:
        return False

    # Must have some trading activity
    if token_info.get("buys_1h", 0) + token_info.get("sells_1h", 0) < 5:
        return False

    # Must be relatively new (less than 7 days)
    if token_info.get("is_new", False) or token_info.get("age", "").endswith("m") or token_info.get("age", "").endswith("h"):
        return True

    # Check if age in days is less than 7
    age = token_info.get("age", "")
    if "d" in age:
        try:
            days = int(age.split("d")[0])
            return days < 7
        except:
            pass

    return True


# ==================== ALERT FORMATTING ====================

def format_sniper_alert(token: dict) -> str:
    """Format a sniper alert message for a new token."""
    name = token.get("name", "Unknown")
    symbol = token.get("symbol", "???")
    price = token.get("price", "0")
    mcap = token.get("market_cap", 0)
    liquidity = token.get("liquidity", 0)
    volume_1h = token.get("volume_1h", 0)
    change_5m = token.get("change_5m", 0)
    change_1h = token.get("change_1h", 0)
    buys_1h = token.get("buys_1h", 0)
    sells_1h = token.get("sells_1h", 0)
    age = token.get("age", "Unknown")
    platform = token.get("platform", "unknown")
    address = token.get("address", "")
    url = token.get("url", "")

    # Platform emoji
    plat_map = {
        "pump_fun": "🎰 Pump.fun",
        "raydium": "💧 Raydium",
        "jupiter": "🪐 Jupiter",
        "unknown": "🔗 Unknown DEX",
    }
    plat_name = plat_map.get(platform, "🔗 DEX")

    # Buy ratio
    total_txns = buys_1h + sells_1h
    buy_ratio = (buys_1h / total_txns * 100) if total_txns > 0 else 50

    # Momentum indicator
    if change_5m > 20:
        momentum = "🚀 PUMPING"
    elif change_5m > 5:
        momentum = "📈 Rising"
    elif change_5m > 0:
        momentum = "↗️ Slight up"
    elif change_5m > -5:
        momentum = "↘️ Slight dip"
    else:
        momentum = "📉 Dropping"

    short_addr = f"{address[:6]}...{address[-4:]}" if len(address) > 10 else address

    text = (
        f"🎯 NEW TOKEN ALERT\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 {name} (${symbol})\n"
        f"📋 {short_addr}\n"
        f"🏷 Platform: {plat_name}\n"
        f"⏱ Age: {age}\n\n"
        f"💰 Price: ${price}\n"
        f"📊 Market Cap: ${mcap:,.0f}\n"
        f"💧 Liquidity: ${liquidity:,.0f}\n"
        f"📈 1h Volume: ${volume_1h:,.0f}\n\n"
        f"⚡ 5m Change: {'+' if change_5m >= 0 else ''}{change_5m:.1f}%\n"
        f"🕐 1h Change: {'+' if change_1h >= 0 else ''}{change_1h:.1f}%\n"
        f"🔄 1h Txns: {buys_1h} buys / {sells_1h} sells ({buy_ratio:.0f}% buy)\n"
        f"📊 Momentum: {momentum}\n\n"
    )

    if url:
        text += f"🔗 DexScreener: {url}\n\n"

    text += (
        f"⚠️ DYOR — This is an automated alert, not financial advice.\n\n"
        f"Powered by kodarkweb3 | For help & collaboration @yms56"
    )

    return text


def get_platform_emoji(platform: str) -> str:
    """Get emoji for a platform."""
    emojis = {
        "pump_fun": "🎰",
        "raydium": "💧",
        "jupiter": "🪐",
        "all": "🌐",
    }
    return emojis.get(platform, "🔗")
