"""
kodark.io - Solana Memecoins Analyzer Bot v5.2
Whale Watch | Holder Analysis | Risk Assessment | Price Alarms
Auto-Sniper Alerts | Multi-Language | Advanced Charting
Smart Money Wallet Tracker | Daily Market Summary | Trending Top 10
Token Watchlist | Alerts Hub | Dark Theme UI
Free Tier (3 analyses + 3 alarms) | Feedback System
Telegram Stars Payment System
"""

import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
    ContextTypes,
)

from api_client import (
    get_token_info,
    get_rugcheck_info,
    get_fear_greed_index,
    get_btc_dominance,
    get_solana_price,
)
from ai_analyzer import analyze_token
from alarm_manager import (
    add_price_alarm,
    get_user_alarms,
    delete_alarm,
    delete_all_alarms,
    check_alarms,
    get_all_watched_tokens,
    format_alarm_text,
)
from whale_monitor import (
    add_whale_alert,
    get_user_whale_alerts,
    delete_whale_alert,
    delete_all_whale_alerts,
    get_all_whale_tokens,
    check_whale_activity,
    format_whale_alert_text,
)
from sniper_alerts import (
    subscribe_sniper,
    unsubscribe_sniper,
    get_user_sniper_status,
    get_all_sniper_subscribers,
    check_new_tokens,
    format_sniper_alert,
    PLATFORM_OPTIONS,
    get_platform_emoji,
)
from chart_generator import generate_price_chart
from languages import (
    get_text,
    get_all_lang_buttons,
    get_lang_name,
    SUPPORTED_LANGUAGES,
    DEFAULT_LANG,
)

# ==================== SETUP ====================

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not found! Check your .env file.")

PREMIUM_PRICE_STARS = 1520  # ~$21.99
PREMIUM_DAYS = 30
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))

# SOL Payment System
SOL_WALLET_ADDRESS = "E3mCsp2GqEt2QpC99DwCsp9PfAumMFLSas5Z9p7MK2xP"
SOL_PAYMENT_CHECK_INTERVAL = 60  # seconds

# Premium Plans (SOL prices in USD equivalent)
PREMIUM_PLANS = {
    "1_month": {"days": 30, "price_usd": 18.49, "label": "1 Month", "stars": 1280},
    "3_month": {"days": 90, "price_usd": 44.99, "label": "3 Months", "stars": 3840},
    "6_month": {"days": 180, "price_usd": 86.99, "label": "6 Months", "stars": 7680},
    "12_month": {"days": 365, "price_usd": 154.99, "label": "1 Year", "stars": 15360},
}

# Campaign: Buy 1 Get 1 Free
CAMPAIGN_BUY1_GET1 = True  # Admin can toggle this

# Free tier limits
FREE_ANALYSIS_LIMIT = 3
FREE_ALARM_LIMIT = 3

# Smart Money Wallet Tracker limits
MAX_TRACKED_WALLETS_PREMIUM = 5
WALLET_CHECK_INTERVAL = 180  # seconds (3 minutes)

# Daily Market Summary
DAILY_SUMMARY_HOUR = 9  # UTC hour to send daily summary
DAILY_SUMMARY_ENABLED = True

# ==================== PERSISTENT DATA STORAGE ====================
# Uses GitHub API to persist data across Railway redeployments.
# Requires GITHUB_TOKEN env variable with repo write access.
# Data is stored in the 'data' branch of the same repo.

import base64
import requests as http_requests

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "kodarkweb3/koanalyzer-bot")
GITHUB_BRANCH = os.getenv("GITHUB_DATA_BRANCH", "data")

# Local cache to reduce API calls
_user_data_cache = None
_feedback_cache = None
_user_data_sha = None
_feedback_sha = None


def _github_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }


def _github_read_file(filename: str) -> tuple:
    """Read a file from GitHub data branch. Returns (content_dict_or_list, sha)."""
    if not GITHUB_TOKEN:
        logger.warning("GITHUB_TOKEN not set, using local file fallback")
        return None, None
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}?ref={GITHUB_BRANCH}"
        resp = http_requests.get(url, headers=_github_headers(), timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            return json.loads(content), data["sha"]
        elif resp.status_code == 404:
            # File or branch doesn't exist yet
            return None, None
        else:
            logger.error(f"GitHub read error {resp.status_code}: {resp.text[:200]}")
            return None, None
    except Exception as e:
        logger.error(f"GitHub read exception: {e}")
        return None, None


def _github_write_file(filename: str, content, sha=None):
    """Write content to GitHub data branch."""
    if not GITHUB_TOKEN:
        logger.warning("GITHUB_TOKEN not set, skipping GitHub write")
        return
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"
        content_str = json.dumps(content, indent=2, default=str)
        encoded = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")
        payload = {
            "message": f"Auto-update {filename}",
            "content": encoded,
            "branch": GITHUB_BRANCH,
        }
        if sha:
            payload["sha"] = sha
        resp = http_requests.put(url, headers=_github_headers(), json=payload, timeout=15)
        if resp.status_code in (200, 201):
            return resp.json().get("content", {}).get("sha")
        elif resp.status_code == 404 and not sha:
            # Branch might not exist, create it
            _ensure_data_branch()
            resp = http_requests.put(url, headers=_github_headers(), json=payload, timeout=15)
            if resp.status_code in (200, 201):
                return resp.json().get("content", {}).get("sha")
        logger.error(f"GitHub write error {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.error(f"GitHub write exception: {e}")
    return None


def _ensure_data_branch():
    """Create the data branch if it doesn't exist."""
    try:
        # Get main branch SHA
        url = f"https://api.github.com/repos/{GITHUB_REPO}/git/ref/heads/main"
        resp = http_requests.get(url, headers=_github_headers(), timeout=10)
        if resp.status_code != 200:
            return
        main_sha = resp.json()["object"]["sha"]
        # Create data branch
        url = f"https://api.github.com/repos/{GITHUB_REPO}/git/refs"
        payload = {"ref": f"refs/heads/{GITHUB_BRANCH}", "sha": main_sha}
        http_requests.post(url, headers=_github_headers(), json=payload, timeout=10)
    except Exception as e:
        logger.error(f"Branch creation error: {e}")


# Local file fallback (used when GITHUB_TOKEN is not set)
DATA_DIR = os.getenv("DATA_DIR", ".")
os.makedirs(DATA_DIR, exist_ok=True)
DATA_FILE = os.path.join(DATA_DIR, "user_data.json")
FEEDBACK_FILE = os.path.join(DATA_DIR, "feedback.json")


def load_user_data() -> dict:
    global _user_data_cache, _user_data_sha
    # Return cache if available
    if _user_data_cache is not None:
        return _user_data_cache
    # Try GitHub first
    if GITHUB_TOKEN:
        content, sha = _github_read_file("user_data.json")
        if content is not None:
            _user_data_cache = content
            _user_data_sha = sha
            return content
    # Fallback to local file
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f:
                _user_data_cache = json.load(f)
                return _user_data_cache
    except Exception as e:
        logger.error(f"Data load error: {e}")
    _user_data_cache = {}
    return {}


def save_user_data(data: dict):
    global _user_data_cache, _user_data_sha
    _user_data_cache = data
    # Save to local file
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Local data save error: {e}")
    # Save to GitHub
    if GITHUB_TOKEN:
        new_sha = _github_write_file("user_data.json", data, _user_data_sha)
        if new_sha:
            _user_data_sha = new_sha


def load_feedback() -> list:
    global _feedback_cache, _feedback_sha
    if _feedback_cache is not None:
        return _feedback_cache
    # Try GitHub first
    if GITHUB_TOKEN:
        content, sha = _github_read_file("feedback.json")
        if content is not None:
            _feedback_cache = content
            _feedback_sha = sha
            return content
    # Fallback to local file
    try:
        if os.path.exists(FEEDBACK_FILE):
            with open(FEEDBACK_FILE, "r") as f:
                _feedback_cache = json.load(f)
                return _feedback_cache
    except Exception as e:
        logger.error(f"Feedback load error: {e}")
    _feedback_cache = []
    return []


def save_feedback(feedbacks: list):
    global _feedback_cache, _feedback_sha
    _feedback_cache = feedbacks
    # Save to local file
    try:
        with open(FEEDBACK_FILE, "w") as f:
            json.dump(feedbacks, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Local feedback save error: {e}")
    # Save to GitHub
    if GITHUB_TOKEN:
        new_sha = _github_write_file("feedback.json", feedbacks, _feedback_sha)
        if new_sha:
            _feedback_sha = new_sha


# ==================== USER HELPERS ====================

def get_user_lang(user_id: int) -> str:
    data = load_user_data()
    user_str = str(user_id)
    if user_str in data:
        return data[user_str].get("lang", DEFAULT_LANG)
    return DEFAULT_LANG


def set_user_lang(user_id: int, lang: str):
    data = load_user_data()
    user_str = str(user_id)
    if user_str not in data:
        data[user_str] = _new_user_record()
    data[user_str]["lang"] = lang
    save_user_data(data)


def _new_user_record() -> dict:
    return {
        "premium": False,
        "premium_until": None,
        "analysis_count": 0,
        "alarm_count": 0,
        "paid_premium": False,
        "joined": datetime.now().isoformat(),
        "watchlist": [],  # Token watchlist [{"address": ..., "symbol": ..., "name": ..., "added": ...}]
        "pending_sol_payment": None,  # {"plan": ..., "amount_sol": ..., "created": ..., "memo": ...}
    }


def ensure_user(user_id: int) -> dict:
    """Ensure user record exists and return it."""
    data = load_user_data()
    user_str = str(user_id)
    if user_str not in data:
        data[user_str] = _new_user_record()
        save_user_data(data)
    return data[user_str]


def get_user_premium_status(user_id: int) -> dict:
    if user_id == ADMIN_USER_ID:
        return {"is_premium": True, "remaining": "Unlimited", "until": "Lifetime"}

    data = load_user_data()
    user_str = str(user_id)

    if user_str not in data:
        data[user_str] = _new_user_record()
        save_user_data(data)

    user = data[user_str]

    if user.get("premium_until"):
        try:
            until = datetime.fromisoformat(user["premium_until"])
            if until > datetime.now():
                remaining = until - datetime.now()
                return {
                    "is_premium": True,
                    "remaining": f"{remaining.days}d {remaining.seconds // 3600}h",
                    "until": until.strftime("%d.%m.%Y %H:%M"),
                }
            else:
                user["premium"] = False
                user["premium_until"] = None
                data[user_str] = user
                save_user_data(data)
        except Exception:
            pass

    return {"is_premium": user.get("premium", False), "remaining": None, "until": None}


def activate_premium(user_id: int, days: int = 30):
    data = load_user_data()
    user_str = str(user_id)

    if user_str not in data:
        data[user_str] = _new_user_record()

    current_until = None
    if data[user_str].get("premium_until"):
        try:
            current_until = datetime.fromisoformat(data[user_str]["premium_until"])
            if current_until < datetime.now():
                current_until = None
        except Exception:
            pass

    base = current_until if current_until else datetime.now()
    until = base + timedelta(days=days)
    data[user_str]["premium"] = True
    data[user_str]["premium_until"] = until.isoformat()
    save_user_data(data)
    return until


# ==================== FREE TIER TRACKING ====================

def get_free_usage(user_id: int) -> dict:
    """Get remaining free tier usage for a user."""
    data = load_user_data()
    user_str = str(user_id)
    if user_str not in data:
        return {"analyses_used": 0, "alarms_used": 0,
                "analyses_left": FREE_ANALYSIS_LIMIT, "alarms_left": FREE_ALARM_LIMIT}

    user = data[user_str]
    analyses_used = user.get("analysis_count", 0)
    alarms_used = user.get("alarm_count", 0)

    return {
        "analyses_used": analyses_used,
        "alarms_used": alarms_used,
        "analyses_left": max(0, FREE_ANALYSIS_LIMIT - analyses_used),
        "alarms_left": max(0, FREE_ALARM_LIMIT - alarms_used),
    }


def can_use_free_analysis(user_id: int) -> bool:
    """Check if user can use a free analysis."""
    if user_id == ADMIN_USER_ID:
        return True
    premium = get_user_premium_status(user_id)
    if premium["is_premium"]:
        return True
    usage = get_free_usage(user_id)
    return usage["analyses_left"] > 0


def can_use_free_alarm(user_id: int) -> bool:
    """Check if user can set a free alarm."""
    if user_id == ADMIN_USER_ID:
        return True
    premium = get_user_premium_status(user_id)
    if premium["is_premium"]:
        return True
    usage = get_free_usage(user_id)
    return usage["alarms_left"] > 0


def increment_analysis(user_id: int):
    data = load_user_data()
    user_str = str(user_id)
    if user_str in data:
        data[user_str]["analysis_count"] = data[user_str].get("analysis_count", 0) + 1
        data[user_str]["last_analysis"] = datetime.now().isoformat()
        save_user_data(data)


def increment_alarm_count(user_id: int):
    data = load_user_data()
    user_str = str(user_id)
    if user_str in data:
        data[user_str]["alarm_count"] = data[user_str].get("alarm_count", 0) + 1
        save_user_data(data)


# ==================== FEEDBACK SYSTEM ====================

def add_feedback(user_id: int, username: str, text: str):
    feedbacks = load_feedback()
    feedbacks.append({
        "user_id": user_id,
        "username": username,
        "text": text,
        "time": datetime.now().isoformat(),
        "read": False,
    })
    save_feedback(feedbacks)


def get_all_feedback() -> list:
    return load_feedback()


def get_unread_feedback_count() -> int:
    feedbacks = load_feedback()
    return sum(1 for f in feedbacks if not f.get("read", False))


def mark_all_feedback_read():
    feedbacks = load_feedback()
    for f in feedbacks:
        f["read"] = True
    save_feedback(feedbacks)


# ==================== SMART MONEY WALLET TRACKER ====================

def get_tracked_wallets(user_id: int) -> list:
    """Get list of wallets tracked by a user."""
    data = load_user_data()
    user_str = str(user_id)
    if user_str not in data:
        return []
    return data[user_str].get("tracked_wallets", [])


def add_tracked_wallet(user_id: int, wallet_address: str, label: str = "") -> dict:
    """Add a wallet to track. Returns success/error dict."""
    data = load_user_data()
    user_str = str(user_id)
    if user_str not in data:
        data[user_str] = _new_user_record()

    wallets = data[user_str].get("tracked_wallets", [])

    # Check limit
    if len(wallets) >= MAX_TRACKED_WALLETS_PREMIUM:
        return {"error": f"Maximum {MAX_TRACKED_WALLETS_PREMIUM} wallets allowed."}

    # Check duplicate
    for w in wallets:
        if w["address"] == wallet_address:
            return {"error": "This wallet is already being tracked."}

    # Validate address format (Solana addresses are 32-44 chars base58)
    if len(wallet_address) < 32 or len(wallet_address) > 50:
        return {"error": "Invalid Solana wallet address."}

    wallet_entry = {
        "address": wallet_address,
        "label": label or f"Wallet #{len(wallets) + 1}",
        "added": datetime.now().isoformat(),
        "last_checked": None,
        "last_tx_signature": None,
    }
    wallets.append(wallet_entry)
    data[user_str]["tracked_wallets"] = wallets
    save_user_data(data)
    return {"success": True, "wallet": wallet_entry, "total": len(wallets)}


def remove_tracked_wallet(user_id: int, wallet_address: str) -> bool:
    """Remove a tracked wallet."""
    data = load_user_data()
    user_str = str(user_id)
    if user_str not in data:
        return False
    wallets = data[user_str].get("tracked_wallets", [])
    original_len = len(wallets)
    wallets = [w for w in wallets if w["address"] != wallet_address]
    if len(wallets) == original_len:
        return False
    data[user_str]["tracked_wallets"] = wallets
    save_user_data(data)
    return True


def remove_all_tracked_wallets(user_id: int) -> int:
    """Remove all tracked wallets. Returns count removed."""
    data = load_user_data()
    user_str = str(user_id)
    if user_str not in data:
        return 0
    count = len(data[user_str].get("tracked_wallets", []))
    data[user_str]["tracked_wallets"] = []
    save_user_data(data)
    return count


def get_all_wallet_trackers() -> dict:
    """Get all users with tracked wallets. Returns {user_id: [wallets]}."""
    data = load_user_data()
    result = {}
    for user_str, ud in data.items():
        if user_str.startswith("__"):
            continue
        wallets = ud.get("tracked_wallets", [])
        if wallets:
            result[user_str] = wallets
    return result


def update_wallet_last_tx(user_id: int, wallet_address: str, signature: str):
    """Update the last known transaction signature for a tracked wallet."""
    data = load_user_data()
    user_str = str(user_id)
    if user_str not in data:
        return
    wallets = data[user_str].get("tracked_wallets", [])
    for w in wallets:
        if w["address"] == wallet_address:
            w["last_tx_signature"] = signature
            w["last_checked"] = datetime.now().isoformat()
            break
    data[user_str]["tracked_wallets"] = wallets
    save_user_data(data)


# Free Solana RPC endpoints (rotate to avoid rate limits)
SOLANA_RPC_ENDPOINTS = [
    "https://api.mainnet-beta.solana.com",
    "https://rpc.ankr.com/solana",
]
_rpc_index = 0


def _get_solana_rpc_url() -> str:
    """Get next Solana RPC endpoint (round-robin)."""
    global _rpc_index
    url = SOLANA_RPC_ENDPOINTS[_rpc_index % len(SOLANA_RPC_ENDPOINTS)]
    _rpc_index += 1
    return url


async def check_wallet_transactions(wallet_address: str, last_signature: str = None) -> list:
    """Check recent transactions for a wallet using free Solana RPC (no API key needed)."""
    try:
        url = _get_solana_rpc_url()
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [
                wallet_address,
                {"limit": 5}
            ]
        }
        if last_signature:
            payload["params"][1]["until"] = last_signature

        resp = http_requests.post(url, json=payload, timeout=15)

        # If rate limited, try fallback RPC
        if resp.status_code == 429 or resp.status_code != 200:
            fallback_url = _get_solana_rpc_url()
            resp = http_requests.post(fallback_url, json=payload, timeout=15)
            if resp.status_code != 200:
                return []

        data = resp.json()
        if "error" in data:
            logger.warning(f"RPC error for {wallet_address[:8]}: {data['error']}")
            return []

        result = data.get("result", [])
        if not result:
            return []

        # Get transaction details for new transactions
        new_txs = []
        for sig_info in result[:3]:  # Max 3 new txs at a time
            sig = sig_info.get("signature")
            if sig == last_signature:
                break
            new_txs.append({
                "signature": sig,
                "slot": sig_info.get("slot"),
                "block_time": sig_info.get("blockTime"),
                "err": sig_info.get("err"),
            })

        return new_txs

    except Exception as e:
        logger.error(f"Wallet tx check error for {wallet_address}: {e}")
        return []


async def get_transaction_details(signature: str) -> dict:
    """Get parsed transaction details from free Solana RPC."""
    try:
        url = _get_solana_rpc_url()
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                signature,
                {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
            ]
        }
        resp = http_requests.post(url, json=payload, timeout=10)
        if resp.status_code != 200:
            return {}

        result = resp.json().get("result")
        if not result:
            return {}

        # Parse basic info
        meta = result.get("meta", {})
        pre_balances = meta.get("preBalances", [])
        post_balances = meta.get("postBalances", [])

        # Detect token transfers
        pre_token = meta.get("preTokenBalances", [])
        post_token = meta.get("postTokenBalances", [])

        tx_type = "unknown"
        details = ""

        # Simple SOL transfer detection
        if pre_balances and post_balances:
            sol_change = (post_balances[0] - pre_balances[0]) / 1_000_000_000
            if abs(sol_change) > 0.01:
                if sol_change > 0:
                    tx_type = "receive_sol"
                    details = f"+{sol_change:.4f} SOL"
                else:
                    tx_type = "send_sol"
                    details = f"{sol_change:.4f} SOL"

        # Token swap/transfer detection
        if post_token and pre_token:
            for pt in post_token:
                mint = pt.get("mint", "")
                ui_amount = pt.get("uiTokenAmount", {}).get("uiAmount", 0)
                # Find matching pre-balance
                pre_amount = 0
                for prt in pre_token:
                    if prt.get("mint") == mint:
                        pre_amount = prt.get("uiTokenAmount", {}).get("uiAmount", 0)
                        break
                if ui_amount and pre_amount is not None:
                    change = (ui_amount or 0) - (pre_amount or 0)
                    if change > 0:
                        tx_type = "buy_token"
                        details = f"Bought token {mint[:8]}..."
                    elif change < 0:
                        tx_type = "sell_token"
                        details = f"Sold token {mint[:8]}..."

        return {
            "signature": signature,
            "type": tx_type,
            "details": details,
            "fee": meta.get("fee", 0) / 1_000_000_000,
            "success": meta.get("err") is None,
        }

    except Exception as e:
        logger.error(f"Transaction detail error for {signature}: {e}")
        return {"signature": signature, "type": "unknown", "details": "Could not parse", "fee": 0, "success": True}


# ==================== DAILY MARKET SUMMARY ====================

def get_daily_summary_subscribers() -> list:
    """Get all premium users who should receive daily summary."""
    data = load_user_data()
    now = datetime.now()
    subscribers = []
    for user_str, ud in data.items():
        if user_str.startswith("__"):
            continue
        # Only premium users get daily summary
        if ud.get("premium_until"):
            try:
                until = datetime.fromisoformat(ud["premium_until"])
                if until > now:
                    # Check if user hasn't opted out
                    if ud.get("daily_summary", True):  # Default enabled for premium
                        subscribers.append(int(user_str))
            except Exception:
                pass
    return subscribers


def toggle_daily_summary(user_id: int) -> bool:
    """Toggle daily summary for a user. Returns new state."""
    data = load_user_data()
    user_str = str(user_id)
    if user_str not in data:
        return False
    current = data[user_str].get("daily_summary", True)
    data[user_str]["daily_summary"] = not current
    save_user_data(data)
    return not current


async def build_daily_summary_text() -> str:
    """Build the daily market summary message."""
    try:
        fng = get_fear_greed_index()
        btc = get_btc_dominance()
        sol = get_solana_price()

        # Fear & Greed
        fng_text = "N/A"
        if "error" not in fng:
            fng_text = f"{fng['emoji']} {fng['value']}/100 - {fng['classification']}"

        # BTC Dominance
        btc_text = "N/A"
        mcap_text = "N/A"
        mcap_change = "N/A"
        if "error" not in btc:
            btc_text = f"{btc['btc_dominance']}%"
            total_mcap = btc.get("total_market_cap", 0)
            if total_mcap > 1_000_000_000_000:
                mcap_text = f"${total_mcap/1_000_000_000_000:.2f}T"
            elif total_mcap > 1_000_000_000:
                mcap_text = f"${total_mcap/1_000_000_000:.2f}B"
            mcap_change = f"{btc.get('market_cap_change_24h', 'N/A')}%"

        # SOL Price
        sol_text = "N/A"
        sol_change = ""
        if "error" not in sol:
            change_emoji = "\U0001f7e2" if sol["change_24h"] >= 0 else "\U0001f534"
            sol_text = f"${sol['price']:.2f}"
            sol_change = f"{change_emoji} {sol['change_24h']:+.2f}%"

        # Market mood
        mood = "Neutral"
        if "error" not in fng:
            val = int(fng.get("value", 50))
            if val >= 75:
                mood = "Extreme Greed - Be cautious with entries"
            elif val >= 55:
                mood = "Greed - Market is optimistic"
            elif val >= 45:
                mood = "Neutral - Watch for breakouts"
            elif val >= 25:
                mood = "Fear - Potential buying opportunities"
            else:
                mood = "Extreme Fear - High risk, high reward zone"

        today = datetime.now().strftime("%d %B %Y")

        summary = (
            f"\U0001f4ca DAILY MARKET SUMMARY\n"
            f"\U0001f4c5 {today}\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            f"\u25ce SOL: {sol_text} {sol_change}\n"
            f"\u20bf BTC Dominance: {btc_text}\n"
            f"\U0001f30d Total Market Cap: {mcap_text}\n"
            f"\U0001f4c8 24h Change: {mcap_change}\n\n"
            f"\U0001f631 Fear & Greed: {fng_text}\n\n"
            f"\U0001f4a1 Market Mood: {mood}\n\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"\U0001f4ce Tip: Use /start to analyze any Solana token\n"
            f"\U0001f514 Disable: Settings > Daily Summary\n\n"
            f"\u2014 kodark.io Premium"
        )
        return summary

    except Exception as e:
        logger.error(f"Daily summary build error: {e}")
        return ""


# ==================== ACTIVITY TRACKING ====================

def record_user_activity(user_id: int, username: str = None, activity: str = "visit"):
    data = load_user_data()
    user_str = str(user_id)
    now = datetime.now().isoformat()

    if user_str not in data:
        data[user_str] = _new_user_record()

    data[user_str]["last_active"] = now
    data[user_str]["username"] = username or data[user_str].get("username", "Unknown")

    if "activity_log" not in data[user_str]:
        data[user_str]["activity_log"] = []
    data[user_str]["activity_log"].append({"type": activity, "time": now})
    data[user_str]["activity_log"] = data[user_str]["activity_log"][-5:]

    if "__stats__" not in data:
        data["__stats__"] = {
            "total_analyses": 0, "total_payments": 0,
            "daily_analyses": {}, "daily_users": {},
        }

    today = datetime.now().strftime("%Y-%m-%d")

    if activity == "analysis":
        data["__stats__"]["total_analyses"] = data["__stats__"].get("total_analyses", 0) + 1
        data["__stats__"]["daily_analyses"][today] = data["__stats__"]["daily_analyses"].get(today, 0) + 1
    if activity == "payment":
        data["__stats__"]["total_payments"] = data["__stats__"].get("total_payments", 0) + 1

    if today not in data["__stats__"]["daily_users"]:
        data["__stats__"]["daily_users"][today] = []
    if user_str not in data["__stats__"]["daily_users"][today]:
        data["__stats__"]["daily_users"][today].append(user_str)

    for key in ["daily_analyses", "daily_users"]:
        dates = sorted(data["__stats__"][key].keys())
        while len(dates) > 30:
            del data["__stats__"][key][dates.pop(0)]

    save_user_data(data)


def get_admin_stats() -> dict:
    data = load_user_data()
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    total_users = 0
    premium_users = 0
    active_today = 0
    active_24h = 0
    new_today = 0
    total_analyses = 0
    free_users = 0
    recent_users = []

    for user_str, ud in data.items():
        if user_str.startswith("__"):
            continue
        total_users += 1
        total_analyses += ud.get("analysis_count", 0)

        is_prem = False
        if ud.get("premium_until"):
            try:
                until = datetime.fromisoformat(ud["premium_until"])
                if until > now:
                    premium_users += 1
                    is_prem = True
            except Exception:
                pass

        if not is_prem:
            free_users += 1

        last_active = ud.get("last_active")
        if last_active:
            try:
                la = datetime.fromisoformat(last_active)
                if la.strftime("%Y-%m-%d") == today:
                    active_today += 1
                if (now - la).total_seconds() < 86400:
                    active_24h += 1
            except Exception:
                pass

        joined = ud.get("joined")
        if joined:
            try:
                jd = datetime.fromisoformat(joined)
                if jd.strftime("%Y-%m-%d") == today:
                    new_today += 1
            except Exception:
                pass

        recent_users.append({
            "id": user_str,
            "username": ud.get("username", "Unknown"),
            "analyses": ud.get("analysis_count", 0),
            "premium": is_prem,
            "paid": ud.get("paid_premium", False),
            "last_active": last_active or joined or "",
            "joined": joined or "",
        })

    recent_users.sort(key=lambda x: x.get("last_active", ""), reverse=True)

    stats = data.get("__stats__", {})
    today_analyses = stats.get("daily_analyses", {}).get(today, 0)
    today_unique = len(stats.get("daily_users", {}).get(today, []))

    week_analyses = []
    for i in range(6, -1, -1):
        d = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        count = stats.get("daily_analyses", {}).get(d, 0)
        day_name = (now - timedelta(days=i)).strftime("%a")
        week_analyses.append(f"{day_name}: {count}")

    unread_fb = get_unread_feedback_count()

    return {
        "total_users": total_users, "premium_users": premium_users,
        "free_users": free_users,
        "active_today": active_today, "active_24h": active_24h,
        "new_today": new_today,
        "total_analyses": total_analyses, "today_analyses": today_analyses,
        "today_unique": today_unique,
        "total_payments": stats.get("total_payments", 0),
        "week_trend": " | ".join(week_analyses),
        "recent_users": recent_users[:10],
        "unread_feedback": unread_fb,
    }


# ==================== ACCESS CHECK ====================

def _check_analysis_access(user_id: int, lang: str = "en") -> str:
    """Check if user can perform analysis. Returns empty string if allowed, paywall text if not."""
    premium = get_user_premium_status(user_id)
    if premium["is_premium"]:
        return ""

    usage = get_free_usage(user_id)
    if usage["analyses_left"] > 0:
        return ""

    # Free tier exhausted
    return (
        f"🔒 Free Analyses Used Up\n\n"
        f"You have used all {FREE_ANALYSIS_LIMIT} free analyses.\n\n"
        f"💎 Upgrade to Premium for unlimited access!\n\n"
        f"Premium includes:\n"
        f"🔍 Unlimited token analysis\n"
        f"🤖 AI-powered reports\n"
        f"🐋 Whale tracking & alerts\n"
        f"⏰ Unlimited price alarms\n"
        f"🎯 Auto-Sniper alerts\n"
        f"📊 Advanced charts\n\n"
        f"From $18.49/month with SOL or {PREMIUM_PLANS['1_month']['stars']} Stars\n\n"
        f"Tap below to upgrade:"
    )


def _check_alarm_access(user_id: int, lang: str = "en") -> str:
    """Check if user can set alarm. Returns empty string if allowed, paywall text if not."""
    premium = get_user_premium_status(user_id)
    if premium["is_premium"]:
        return ""

    usage = get_free_usage(user_id)
    if usage["alarms_left"] > 0:
        return ""

    return (
        f"🔒 Free Alarms Used Up\n\n"
        f"You have used all {FREE_ALARM_LIMIT} free price alarms.\n\n"
        f"💎 Upgrade to Premium for unlimited alarms!\n\n"
        f"From $18.49/month with SOL or {PREMIUM_PLANS['1_month']['stars']} Stars\n\n"
        f"Tap below to upgrade:"
    )


def _check_premium_only(user_id: int, feature: str = "This feature") -> str:
    """Check if user has premium for premium-only features (whale, sniper, signals)."""
    premium = get_user_premium_status(user_id)
    if premium["is_premium"]:
        return ""

    return (
        f"🔒 Premium Feature\n\n"
        f"{feature} is only available for Premium subscribers.\n\n"
        f"Free users get:\n"
        f"🔍 {FREE_ANALYSIS_LIMIT} token analyses\n"
        f"⏰ {FREE_ALARM_LIMIT} price alarms\n\n"
        f"💎 Upgrade to Premium to unlock everything!\n\n"
        f"From $18.49/month with SOL or {PREMIUM_PLANS['1_month']['stars']} Stars\n\n"
        f"Tap below to upgrade:"
    )


# ==================== START MENU ====================

def build_start_text(premium: dict, lang: str = "en", user_id: int = None) -> str:
    if premium["is_premium"]:
        if premium["remaining"] == "Unlimited":
            status_line = f"Premium Status: Active (Lifetime) \u2705"
        else:
            status_line = f"Premium Status: Active ({premium['remaining']} left) \u2705"
    else:
        usage = get_free_usage(user_id) if user_id else {"analyses_left": FREE_ANALYSIS_LIMIT, "alarms_left": FREE_ALARM_LIMIT}
        status_line = (
            f"Premium Status: Inactive\n"
            f"Free: {usage['analyses_left']}/{FREE_ANALYSIS_LIMIT} analyses | {usage['alarms_left']}/{FREE_ALARM_LIMIT} alarms"
        )

    # Campaign banner
    campaign_banner = ""
    if CAMPAIGN_BUY1_GET1 and not premium["is_premium"]:
        campaign_banner = (
            f"\n\U0001f0cf Buy 1 Month Premium, Get 1 Month FREE\n"
            f"Limited time offer. Pay with SOL or Stars.\n"
        )

    text = (
        f"Welcome to \U0001D5F8\U0001D5FC\U0001D5F1\U0001D5EE\U0001D5FF\U0001D5F8.\U0001D5F6\U0001D5FC \U0001f0cf\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        f"Solana memecoin intelligence tool.\n"
        f"Analyze tokens, detect risks, and track smart money \u2014 all within Telegram.\n\n"
        f"What you can do with \U0001D5F8\U0001D5FC\U0001D5F1\U0001D5EE\U0001D5FF\U0001D5F8.\U0001D5F6\U0001D5FC? \U0001f0cf\n\n"
        f"Token Analysis \U0001f50d: Full risk scoring, holder distribution, and liquidity checks\n\n"
        f"Smart Money \U0001f4b0: Track profitable wallets and see their trades in real-time\n\n"
        f"Trending \U0001f4c8: Top performing Solana tokens ranked by volume\n\n"
        f"Charts \U0001f4ca: Professional price and volume charts inside Telegram\n\n"
        f"Market Signals \U0001f4e1: Fear & Greed Index, BTC dominance, SOL price\n\n"
        f"Alarms? \U0001f0cf\n\n"
        f"Price Alarms \u23f0: Set targets and get notified when price hits your level\n\n"
        f"Whale Alerts \U0001f40b: Detect large wallet movements on any token\n\n"
        f"Sniper Alerts \U0001f3af: New token launch notifications from Pump .fun, Raydium, Jupiter\n\n"
        f"{campaign_banner}"
        f"{status_line}\n\n"
        f"x.com/kodarkweb3\n"
        f"x.com/kodarkio"
    )
    return text


def build_start_keyboard(is_premium: bool, lang: str = "en") -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("START ANALYZING \U0001f0cf", callback_data="start_analyzing")],
        [InlineKeyboardButton("Trending Top 10 \u2666\ufe0f", callback_data="trending_tokens")],
        [InlineKeyboardButton("Smart Money Tracker \u2660\ufe0f", callback_data="wallet_tracker_menu")],
        [InlineKeyboardButton("Alerts Hub \u2663\ufe0f", callback_data="alerts_hub")],
        [InlineKeyboardButton("My Watchlist \u2665\ufe0f", callback_data="watchlist_menu")],
        [InlineKeyboardButton("Market Signals \u2666\ufe0f", callback_data="signals")],
        [InlineKeyboardButton("Premium Status \u2705", callback_data="premium")],
        [InlineKeyboardButton("\U0001f310 Language", callback_data="language_menu")],
        [InlineKeyboardButton("\U0001f5fa Roadmap", callback_data="roadmap")],
        [InlineKeyboardButton("\U0001f4ac Feedback", callback_data="feedback_start")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ==================== COMMANDS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or "Unknown"
    record_user_activity(user_id, username, "visit")
    ensure_user(user_id)
    premium = get_user_premium_status(user_id)
    lang = get_user_lang(user_id)
    text = build_start_text(premium, lang, user_id)
    kb = build_start_keyboard(premium["is_premium"], lang)
    await update.message.reply_text(text, reply_markup=kb, disable_web_page_preview=True)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_lang(user_id)
    help_text = (
        "kodark.io \u2014 Help Guide \U0001f0cf\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        "Commands:\n\n"
        "/start \u2014 Main menu\n"
        "/help \u2014 This help guide\n"
        "/premium \u2014 Premium status\n"
        "/feedback \u2014 Send feedback\n"
        "/admin \u2014 Admin panel (admin only)\n\n"
        "How to Use:\n"
        "1. Tap START ANALYZING\n"
        "2. Enter a Solana memecoin address\n"
        "3. Choose: Analysis, Chart, Price Alarm, or Whale Alert\n\n"
        f"Free Tier: {FREE_ANALYSIS_LIMIT} analyses + {FREE_ALARM_LIMIT} price alarms\n"
        f"Premium: ~$21.99/month for unlimited access\n\n"
        "x.com/kodarkweb3\n"
        "x.com/kodarkio"
    )
    kb = [[InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")]]
    await update.message.reply_text(help_text, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)


async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    premium = get_user_premium_status(user_id)
    text = _build_premium_text(premium, user_id)
    kb = _build_premium_keyboard(premium)
    await update.message.reply_text(text, reply_markup=kb, disable_web_page_preview=True)


async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /feedback command."""
    user_id = update.effective_user.id
    lang = get_user_lang(user_id)
    context.user_data["waiting_for_feedback"] = True
    await update.message.reply_text(
        "💬 FEEDBACK\n"
        "━━━━━━━━━━━━━━━\n\n"
        "We value your feedback!\n\n"
        "Please type your feedback, suggestion, or bug report below.\n"
        "Your message will be sent to the kodark.io team.\n\n"
        "Type your message:",
        disable_web_page_preview=True,
    )


# ==================== PREMIUM TEXT & KEYBOARD ====================

def _build_premium_text(premium: dict, user_id: int = None) -> str:
    if premium["is_premium"]:
        if premium["remaining"] == "Unlimited":
            return (
                f"PREMIUM STATUS\n\n"
                f"Status: Active (Lifetime) \u2705\n\n"
                f"All premium features are unlocked.\n\n"
                f"Thank you for your support."
            )
        else:
            return (
                f"PREMIUM STATUS\n\n"
                f"Status: Active \u2705\n"
                f"Remaining: {premium['remaining']}\n"
                f"Expires: {premium['until']}\n\n"
                f"All premium features are unlocked.\n\n"
                f"Renew before expiry to keep access."
            )
    else:
        usage = get_free_usage(user_id) if user_id else {"analyses_left": FREE_ANALYSIS_LIMIT, "alarms_left": FREE_ALARM_LIMIT}
        campaign_text = ""
        if CAMPAIGN_BUY1_GET1:
            campaign_text = (
                f"\n\U0001f0cf LIMITED OFFER: Buy 1 Month, Get 1 Month FREE\n"
                f"(Campaign active for a limited time)\n"
            )
        return (
            f"PREMIUM STATUS\n\n"
            f"Status: Inactive\n\n"
            f"Free Tier Remaining:\n"
            f"Analyses: {usage['analyses_left']}/{FREE_ANALYSIS_LIMIT}\n"
            f"Alarms: {usage['alarms_left']}/{FREE_ALARM_LIMIT}\n\n"
            f"Premium features:\n"
            f"Unlimited token analysis\n"
            f"AI-powered reports\n"
            f"Whale alert notifications\n"
            f"Unlimited price alarms\n"
            f"Auto-Sniper alerts\n"
            f"Advanced charts\n"
            f"Smart Money Tracker\n"
            f"Daily Market Summary\n\n"
            f"{campaign_text}\n"
            f"\u2501\u2501\u2501 PRICING \u2501\u2501\u2501\n\n"
            f"Pay with SOL (cheaper, no commission):\n"
            f"1 Month: $18.49\n"
            f"3 Months: $44.99 (save 19%)\n"
            f"6 Months: $86.99 (save 22%)\n"
            f"1 Year: $154.99 (save 30%)\n\n"
            f"Pay with Telegram Stars:\n"
            f"1 Month: {PREMIUM_PLANS['1_month']['stars']} Stars (~$21.99)\n"
            f"3 Months: {PREMIUM_PLANS['3_month']['stars']} Stars\n"
            f"6 Months: {PREMIUM_PLANS['6_month']['stars']} Stars\n"
            f"1 Year: {PREMIUM_PLANS['12_month']['stars']} Stars\n\n"
            f"Select a plan below:"
        )


def _build_premium_keyboard(premium: dict) -> InlineKeyboardMarkup:
    if premium["is_premium"]:
        kb = [
            [InlineKeyboardButton("START ANALYZING \U0001f0cf", callback_data="start_analyzing")],
        ]
        if premium["remaining"] != "Unlimited":
            kb.append([InlineKeyboardButton("Renew Premium", callback_data="select_plan")])
        kb.append([InlineKeyboardButton("Main Menu", callback_data="home")])
        return InlineKeyboardMarkup(kb)
    else:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Pay with SOL (Cheaper)", callback_data="pay_sol_select")],
            [InlineKeyboardButton("Pay with Telegram Stars", callback_data="pay_stars_select")],
            [InlineKeyboardButton("Main Menu", callback_data="home")],
        ])


# ==================== PAYMENT SYSTEM (SOL + TELEGRAM STARS) ====================


def _get_sol_price_usd() -> float:
    """Get current SOL price in USD."""
    try:
        sol = get_solana_price()
        if "error" not in sol:
            return sol["price"]
    except Exception:
        pass
    return 0.0


def _calculate_sol_amount(plan_key: str) -> float:
    """Calculate SOL amount needed for a plan based on current SOL price."""
    plan = PREMIUM_PLANS.get(plan_key)
    if not plan:
        return 0.0
    sol_price = _get_sol_price_usd()
    if sol_price <= 0:
        return 0.0
    return round(plan["price_usd"] / sol_price, 4)


def _generate_payment_memo(user_id: int) -> str:
    """Generate unique memo for SOL payment identification."""
    import hashlib
    raw = f"{user_id}_{datetime.now().timestamp()}"
    return hashlib.md5(raw.encode()).hexdigest()[:8]


async def _verify_sol_payment(wallet_address: str, expected_amount: float, memo: str, created_after: str) -> bool:
    """Verify SOL payment by checking recent transactions to our wallet."""
    try:
        url = _get_solana_rpc_url()
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [
                SOL_WALLET_ADDRESS,
                {"limit": 20}
            ]
        }
        resp = http_requests.post(url, json=payload, timeout=15)
        if resp.status_code != 200:
            return False

        data = resp.json()
        if "error" in data:
            return False

        result = data.get("result", [])
        created_ts = datetime.fromisoformat(created_after).timestamp()

        for sig_info in result:
            block_time = sig_info.get("blockTime", 0)
            if block_time < created_ts:
                continue
            if sig_info.get("err"):
                continue

            # Get transaction details
            sig = sig_info.get("signature")
            tx_url = _get_solana_rpc_url()
            tx_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTransaction",
                "params": [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
            }
            tx_resp = http_requests.post(tx_url, json=tx_payload, timeout=10)
            if tx_resp.status_code != 200:
                continue

            tx_result = tx_resp.json().get("result")
            if not tx_result:
                continue

            meta = tx_result.get("meta", {})
            pre_balances = meta.get("preBalances", [])
            post_balances = meta.get("postBalances", [])

            # Check if this is a SOL transfer to our wallet
            account_keys = tx_result.get("transaction", {}).get("message", {}).get("accountKeys", [])
            our_index = -1
            for i, key in enumerate(account_keys):
                pubkey = key.get("pubkey", "") if isinstance(key, dict) else str(key)
                if pubkey == SOL_WALLET_ADDRESS:
                    our_index = i
                    break

            if our_index >= 0 and our_index < len(pre_balances) and our_index < len(post_balances):
                received_lamports = post_balances[our_index] - pre_balances[our_index]
                received_sol = received_lamports / 1_000_000_000
                # Allow 2% tolerance for price fluctuation
                if received_sol >= expected_amount * 0.98:
                    return True

        return False
    except Exception as e:
        logger.error(f"SOL payment verification error: {e}")
        return False


async def send_premium_invoice(update_or_query, context: ContextTypes.DEFAULT_TYPE, plan_key: str = "1_month"):
    """Send Telegram Stars invoice for selected plan."""
    plan = PREMIUM_PLANS.get(plan_key, PREMIUM_PLANS["1_month"])
    if hasattr(update_or_query, 'message') and update_or_query.message:
        chat_id = update_or_query.message.chat_id
    elif hasattr(update_or_query, 'from_user'):
        chat_id = update_or_query.from_user.id
    else:
        chat_id = update_or_query.effective_chat.id

    days_label = plan["days"]

    await context.bot.send_invoice(
        chat_id=chat_id,
        title=f"kodark.io Premium - {plan['label']}",
        description=f"Unlock {days_label}-day Premium Access\n"
                    f"Unlimited analysis, whale alerts, sniper, charts",
        payload=f"premium_{plan_key}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=f"Premium {plan['label']}", amount=plan["stars"])],
    )


async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    if query.invoice_payload.startswith("premium_"):
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Unknown payment type.")


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    user_id = update.effective_user.id

    if payment.invoice_payload.startswith("premium_"):
        plan_key = payment.invoice_payload.replace("premium_", "")
        plan = PREMIUM_PLANS.get(plan_key, PREMIUM_PLANS["1_month"])
        days = plan["days"]

        # Stars payment - no campaign bonus (campaign only for SOL)
        until = activate_premium(user_id, days=days)
        data = load_user_data()
        user_str = str(user_id)
        if user_str in data:
            data[user_str]["paid_premium"] = True
            save_user_data(data)
        username = update.effective_user.username or update.effective_user.first_name or "Unknown"
        record_user_activity(user_id, username, "payment")
        date_str = until.strftime('%d.%m.%Y %H:%M')

        bonus_text = ""

        kb = [
            [InlineKeyboardButton("START ANALYZING \U0001f0cf", callback_data="start_analyzing")],
            [InlineKeyboardButton("Main Menu", callback_data="home")],
        ]
        await update.message.reply_text(
            f"Payment Successful!\n\n"
            f"Your {days}-day Premium subscription is now active \u2705\n"
            f"Expires: {date_str}\n"
            f"{bonus_text}\n\n"
            f"All premium features are unlocked.",
            reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
        )


# ==================== MARKET SIGNALS ====================

async def _send_signals(msg, user_id: int):
    try:
        fng = get_fear_greed_index()
        btc = get_btc_dominance()
        sol = get_solana_price()

        fng_text = "Data unavailable"
        if "error" not in fng:
            fng_text = f"{fng['emoji']} {fng['value']}/100 - {fng['classification']}"

        btc_text = "Data unavailable"
        mcap_text = ""
        if "error" not in btc:
            btc_text = f"{btc['btc_dominance']}%"
            total_mcap = btc.get("total_market_cap", 0)
            if total_mcap > 1_000_000_000_000:
                mcap_text = f"${total_mcap/1_000_000_000_000:.2f}T"
            elif total_mcap > 1_000_000_000:
                mcap_text = f"${total_mcap/1_000_000_000:.2f}B"
            else:
                mcap_text = f"${total_mcap:,.0f}"

        sol_text = "Data unavailable"
        if "error" not in sol:
            change_emoji = "🟢" if sol["change_24h"] >= 0 else "🔴"
            sol_text = f"${sol['price']:.2f} {change_emoji} {sol['change_24h']:+.2f}%"

        signals_text = (
            f"📈 MARKET SIGNALS\n\n"
            f"😱 Fear & Greed Index:\n{fng_text}\n\n"
            f"₿ BTC Dominance: {btc_text}\n\n"
            f"◎ SOL Price: {sol_text}\n\n"
            f"🌍 Total Market Cap: {mcap_text}\n"
            f"24h Change: {btc.get('market_cap_change_24h', 'N/A')}%\n\n"
            f"🕐 Last updated: {datetime.now().strftime('%H:%M:%S UTC')}"
        )

        kb = [
            [InlineKeyboardButton("Refresh", callback_data="signals")],
            [InlineKeyboardButton("START ANALYZING \U0001f0cf", callback_data="start_analyzing")],
            [InlineKeyboardButton("Main Menu", callback_data="home")],
        ]
        await msg.edit_text(signals_text, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Signals error: {e}")
        await msg.edit_text(f"❌ Error fetching market data: {str(e)[:200]}")


# ==================== TRENDING TOKENS ====================

async def _fetch_trending_tokens() -> list:
    """Fetch top 10 trending Solana tokens from DexScreener."""
    import aiohttp
    try:
        url = "https://api.dexscreener.com/latest/dex/tokens/solana"
        # Use search endpoint for boosted/trending tokens
        url = "https://api.dexscreener.com/token-boosts/top/v1"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    # Fallback: use pairs sorted by volume
                    fallback_url = "https://api.dexscreener.com/latest/dex/pairs/solana"
                    async with session.get(fallback_url, timeout=aiohttp.ClientTimeout(total=15)) as fb_resp:
                        if fb_resp.status != 200:
                            return []
                        fb_data = await fb_resp.json()
                        pairs = fb_data.get("pairs", [])
                        pairs.sort(key=lambda x: x.get("volume", {}).get("h24", 0), reverse=True)
                        result = []
                        for p in pairs[:10]:
                            result.append({
                                "symbol": p.get("baseToken", {}).get("symbol", "???"),
                                "name": p.get("baseToken", {}).get("name", "Unknown"),
                                "price": float(p.get("priceUsd", 0) or 0),
                                "change_24h": float(p.get("priceChange", {}).get("h24", 0) or 0),
                                "volume_24h": float(p.get("volume", {}).get("h24", 0) or 0),
                                "address": p.get("baseToken", {}).get("address", ""),
                            })
                        return result
                
                data = await resp.json()
                # token-boosts returns a list of boosted tokens
                result = []
                seen = set()
                for item in data:
                    chain = item.get("chainId", "")
                    if chain != "solana":
                        continue
                    addr = item.get("tokenAddress", "")
                    if addr in seen:
                        continue
                    seen.add(addr)
                    # Fetch pair data for this token
                    result.append({
                        "symbol": item.get("symbol", item.get("tokenAddress", "???")[:6]),
                        "name": item.get("name", "Unknown"),
                        "price": 0,
                        "change_24h": 0,
                        "volume_24h": 0,
                        "address": addr,
                    })
                    if len(result) >= 10:
                        break
                
                # If we got boosted tokens, fetch their prices
                if result:
                    addresses = ",".join([t["address"] for t in result[:10]])
                    price_url = f"https://api.dexscreener.com/latest/dex/tokens/{addresses}"
                    async with session.get(price_url, timeout=aiohttp.ClientTimeout(total=15)) as price_resp:
                        if price_resp.status == 200:
                            price_data = await price_resp.json()
                            pairs = price_data.get("pairs", [])
                            # Map address to best pair
                            addr_map = {}
                            for p in pairs:
                                base_addr = p.get("baseToken", {}).get("address", "")
                                if base_addr not in addr_map:
                                    addr_map[base_addr] = p
                                elif float(p.get("volume", {}).get("h24", 0) or 0) > float(addr_map[base_addr].get("volume", {}).get("h24", 0) or 0):
                                    addr_map[base_addr] = p
                            
                            for t in result:
                                if t["address"] in addr_map:
                                    p = addr_map[t["address"]]
                                    t["symbol"] = p.get("baseToken", {}).get("symbol", t["symbol"])
                                    t["name"] = p.get("baseToken", {}).get("name", t["name"])
                                    t["price"] = float(p.get("priceUsd", 0) or 0)
                                    t["change_24h"] = float(p.get("priceChange", {}).get("h24", 0) or 0)
                                    t["volume_24h"] = float(p.get("volume", {}).get("h24", 0) or 0)
                
                # If no solana tokens from boosts, fallback
                if not result:
                    fallback_url = "https://api.dexscreener.com/latest/dex/pairs/solana"
                    async with session.get(fallback_url, timeout=aiohttp.ClientTimeout(total=15)) as fb_resp:
                        if fb_resp.status != 200:
                            return []
                        fb_data = await fb_resp.json()
                        pairs = fb_data.get("pairs", [])
                        pairs.sort(key=lambda x: x.get("volume", {}).get("h24", 0), reverse=True)
                        for p in pairs[:10]:
                            result.append({
                                "symbol": p.get("baseToken", {}).get("symbol", "???"),
                                "name": p.get("baseToken", {}).get("name", "Unknown"),
                                "price": float(p.get("priceUsd", 0) or 0),
                                "change_24h": float(p.get("priceChange", {}).get("h24", 0) or 0),
                                "volume_24h": float(p.get("volume", {}).get("h24", 0) or 0),
                                "address": p.get("baseToken", {}).get("address", ""),
                            })
                
                return result
    except Exception as e:
        logger.error(f"Trending fetch error: {e}")
        return []


# ==================== ADMIN PANEL ====================

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("⛔ Access denied.")
        return
    stats = get_admin_stats()
    text = _build_admin_panel_text(stats)
    kb = _build_admin_keyboard(stats)
    await update.message.reply_text(text, reply_markup=kb, disable_web_page_preview=True)


def _build_admin_panel_text(stats: dict) -> str:
    now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    fb_badge = f" (📩 {stats['unread_feedback']} new)" if stats.get('unread_feedback', 0) > 0 else ""
    return (
        f"📊 ADMIN PANEL{fb_badge}\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"👥 USERS\n"
        f"├ Total Users: {stats['total_users']}\n"
        f"├ Free Tier: {stats['free_users']}\n"
        f"├ New Today: {stats['new_today']}\n"
        f"├ Active Today: {stats['active_today']}\n"
        f"└ Active (24h): {stats['active_24h']}\n\n"
        f"💎 PREMIUM\n"
        f"├ Active Premium: {stats['premium_users']}\n"
        f"└ Total Payments: {stats['total_payments']}\n\n"
        f"🔍 ANALYSES\n"
        f"├ Total: {stats['total_analyses']}\n"
        f"├ Today: {stats['today_analyses']}\n"
        f"└ Today Unique Users: {stats['today_unique']}\n\n"
        f"📈 WEEKLY TREND\n"
        f"{stats['week_trend']}\n\n"
        f"🕐 Updated: {now}"
    )


def _build_admin_keyboard(stats: dict = None) -> InlineKeyboardMarkup:
    fb_count = stats.get("unread_feedback", 0) if stats else 0
    fb_label = f"💬 Feedback ({fb_count} new)" if fb_count > 0 else "💬 Feedback"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh Stats", callback_data="admin_refresh")],
        [InlineKeyboardButton("👥 Recent Users", callback_data="admin_users")],
        [InlineKeyboardButton("💎 Premium Users", callback_data="admin_premium_list")],
        [InlineKeyboardButton("🎁 Premium Hediye Et", callback_data="admin_gift_premium")],
        [InlineKeyboardButton("\U0001f0cf Campaign Management " + ("\U0001f7e2" if CAMPAIGN_BUY1_GET1 else "\U0001f534"), callback_data="admin_campaign")],
        [InlineKeyboardButton("📊 Detailed Analytics", callback_data="admin_analytics")],
        [InlineKeyboardButton(fb_label, callback_data="admin_feedback")],
        [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast_info")],
        [InlineKeyboardButton("Main Menu", callback_data="home")],
    ])


def _build_recent_users_text(stats: dict) -> str:
    text = "👥 RECENT USERS (Last Active)\n━━━━━━━━━━━━━━━\n\n"
    if not stats["recent_users"]:
        text += "No users yet."
        return text
    for i, user in enumerate(stats["recent_users"], 1):
        badge = "💎" if user["premium"] else "🆓"
        paid = "💰" if user.get("paid") else ""
        la = user.get("last_active", "")
        if la:
            try:
                la = datetime.fromisoformat(la).strftime("%d.%m %H:%M")
            except Exception:
                la = "N/A"
        text += f"{i}. {badge} @{user['username']} {paid}\n   ID: {user['id']} | Analyses: {user['analyses']}\n   Last: {la}\n\n"
    return text


def _build_premium_users_text(stats: dict) -> str:
    data = load_user_data()
    now = datetime.now()
    text = "💎 PREMIUM USERS\n━━━━━━━━━━━━━━━\n\n"
    count = 0
    for user_str, ud in data.items():
        if user_str.startswith("__"):
            continue
        if ud.get("premium_until"):
            try:
                until = datetime.fromisoformat(ud["premium_until"])
                if until > now:
                    count += 1
                    remaining = until - now
                    text += f"{count}. @{ud.get('username', 'Unknown')}\n   ID: {user_str}\n   Remaining: {remaining.days}d {remaining.seconds // 3600}h\n   Expires: {until.strftime('%d.%m.%Y %H:%M')}\n\n"
            except Exception:
                pass
    if count == 0:
        text += "No active premium users."
    else:
        text += f"\nTotal: {count} premium user(s)"
    return text


def _build_analytics_text() -> str:
    data = load_user_data()
    stats_data = data.get("__stats__", {})
    now = datetime.now()

    text = "📊 DETAILED ANALYTICS\n━━━━━━━━━━━━━━━\n\n📅 DAILY BREAKDOWN (Last 7 Days)\n\n"
    text += f"{'Date':<12} {'Users':<8} {'Analyses':<10}\n{'─'*30}\n"

    for i in range(6, -1, -1):
        d = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        d_display = (now - timedelta(days=i)).strftime("%d.%m")
        day_name = (now - timedelta(days=i)).strftime("%a")
        users = len(stats_data.get("daily_users", {}).get(d, []))
        analyses = stats_data.get("daily_analyses", {}).get(d, 0)
        marker = " ◀" if i == 0 else ""
        text += f"{day_name} {d_display}   {users:<8} {analyses:<10}{marker}\n"

    total_users = sum(1 for k in data if not k.startswith("__"))
    paid_users = stats_data.get("total_payments", 0)

    text += f"\n💰 CONVERSION\n"
    if total_users > 0:
        text += f"└ Paid Rate: {(paid_users / total_users) * 100:.1f}% ({paid_users}/{total_users})\n"
    else:
        text += "├ No data yet\n"

    revenue = paid_users * 7.99
    text += f"\n💵 ESTIMATED REVENUE\n└ ~${revenue:.2f} ({paid_users} payment(s))\n"
    text += f"\n🕐 Generated: {now.strftime('%d.%m.%Y %H:%M:%S')}"
    return text


def _build_feedback_text() -> str:
    feedbacks = get_all_feedback()
    if not feedbacks:
        return "💬 FEEDBACK\n━━━━━━━━━━━━━━━\n\nNo feedback received yet."

    text = "💬 FEEDBACK\n━━━━━━━━━━━━━━━\n\n"
    # Show last 10 feedbacks
    recent = feedbacks[-10:]
    for i, fb in enumerate(reversed(recent), 1):
        time_str = ""
        try:
            time_str = datetime.fromisoformat(fb["time"]).strftime("%d.%m %H:%M")
        except Exception:
            time_str = "N/A"
        read_mark = "" if fb.get("read") else " 🆕"
        text += f"{i}. @{fb.get('username', 'Unknown')}{read_mark}\n   {time_str}\n   \"{fb['text'][:100]}\"\n\n"

    text += f"Total: {len(feedbacks)} feedback(s)"
    mark_all_feedback_read()
    return text


# ==================== BROADCAST ====================

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("⛔ Access denied.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast Your message here")
        return

    broadcast_text = " ".join(context.args)
    data = load_user_data()
    sent = 0
    failed = 0
    status_msg = await update.message.reply_text("📢 Broadcasting...")

    for user_str in data:
        if user_str.startswith("__"):
            continue
        try:
            await context.bot.send_message(
                chat_id=int(user_str),
                text=f"📢 Announcement\n\n{broadcast_text}\n\n— kodark.io Team",
            )
            sent += 1
        except Exception as e:
            logger.warning(f"Broadcast failed for {user_str}: {e}")
            failed += 1

    await status_msg.edit_text(f"✅ Broadcast Complete!\n\n✔️ Sent: {sent}\n❌ Failed: {failed}\n📬 Total: {sent + failed}")


# ==================== WELCOME MESSAGE ====================

async def welcome_new_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message when a new user joins the bot chat."""
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        await update.message.reply_text(
            "👋 Welcome to kodark.io!\n\n"
            "🚀 The ultimate Solana memecoin analyzer.\n\n"
            f"🆓 Start with {FREE_ANALYSIS_LIMIT} free analyses + {FREE_ALARM_LIMIT} free alarms!\n\n"
            "👉 Type /start to begin!",
            disable_web_page_preview=True,
        )


# ==================== CALLBACK HANDLER ====================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global CAMPAIGN_BUY1_GET1
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang = get_user_lang(user_id)

    # ===== HOME =====
    if query.data == "home":
        premium = get_user_premium_status(user_id)
        text = build_start_text(premium, lang, user_id)
        kb = build_start_keyboard(premium["is_premium"], lang)
        await query.edit_message_text(text, reply_markup=kb, disable_web_page_preview=True)

    # ===== LANGUAGE MENU =====
    elif query.data == "language_menu":
        buttons = get_all_lang_buttons()
        kb_rows = []
        for i in range(0, len(buttons), 3):
            row = []
            for name, cb_data in buttons[i:i+3]:
                row.append(InlineKeyboardButton(name, callback_data=cb_data))
            kb_rows.append(row)
        kb_rows.append([InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")])

        current_lang_name = get_lang_name(lang)
        await query.edit_message_text(
            f"🌐 {get_text('lang_select', lang)}\n\n"
            f"Current: {current_lang_name}\n\n"
            f"Select your preferred language:",
            reply_markup=InlineKeyboardMarkup(kb_rows), disable_web_page_preview=True,
        )

    elif query.data.startswith("lang_"):
        new_lang = query.data.replace("lang_", "")
        if new_lang in SUPPORTED_LANGUAGES:
            set_user_lang(user_id, new_lang)
            lang = new_lang
            lang_name = get_lang_name(new_lang)
            premium = get_user_premium_status(user_id)
            kb = build_start_keyboard(premium["is_premium"], lang)
            await query.edit_message_text(
                f"✅ {get_text('lang_changed', lang)}: {lang_name}\n\n"
                f"{build_start_text(premium, lang, user_id)}",
                reply_markup=kb, disable_web_page_preview=True,
            )

    # ===== START ANALYZING =====
    elif query.data == "start_analyzing":
        # Check free tier or premium
        paywall = _check_analysis_access(user_id, lang)
        if paywall:
            kb = [
                [InlineKeyboardButton("Upgrade Premium - from $18.49", callback_data="buy_premium")],
                [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
            ]
            await query.edit_message_text(paywall, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return

        premium = get_user_premium_status(user_id)
        usage_hint = ""
        if not premium["is_premium"]:
            usage = get_free_usage(user_id)
            usage_hint = f"\n🆓 Free analyses remaining: {usage['analyses_left']}/{FREE_ANALYSIS_LIMIT}\n"

        await query.edit_message_text(
            f"{get_text('btn_start_analyzing', lang)}\n\n"
            f"Paste a Solana token contract address.\n"
            f"{usage_hint}",
            disable_web_page_preview=True,
        )
        context.user_data["waiting_for_token"] = True
        context.user_data["token_flow"] = "choose_action"

    # ===== TOKEN ACTION CHOICES =====
    elif query.data == "action_analysis":
        token_address = context.user_data.get("current_token_address")
        if not token_address:
            await query.edit_message_text("⚠️ Token address lost. Please start again.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Main Menu", callback_data="home")]]))
            return

        # Check analysis access
        paywall = _check_analysis_access(user_id, lang)
        if paywall:
            kb = [
                [InlineKeyboardButton("Upgrade Premium - from $18.49", callback_data="buy_premium")],
                [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
            ]
            await query.edit_message_text(paywall, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return

        await query.edit_message_text(
            f"⏳ {get_text('analysis_progress', lang)}\n\n"
            f"🔄 Fetching DexScreener data...\n"
            f"🔄 Running RugCheck security scan...\n"
            f"🔄 Analyzing whale & holder data...\n"
            f"🔄 Generating comprehensive report...",
            disable_web_page_preview=True,
        )

        try:
            token_data = get_token_info(token_address)
            if "error" in token_data:
                await query.edit_message_text(f"❌ Error: {token_data['error']}")
                return

            rug_data = get_rugcheck_info(token_address)
            if "error" in rug_data:
                rug_data = {
                    "risk_score": None, "risk_level": "UNKNOWN", "risk_emoji": "⚪",
                    "risks": [], "top_holders": [], "total_insider_pct": 0,
                    "total_top10_pct": 0,
                    "mint_authority": None, "freeze_authority": None, "is_mutable": None,
                }

            report = analyze_token(token_data, rug_data)
            increment_analysis(user_id)
            username = query.from_user.username or query.from_user.first_name or "Unknown"
            record_user_activity(user_id, username, "analysis")

            dex_url = token_data.get("url", f"https://dexscreener.com/solana/{token_address}")
            kb = [
                [InlineKeyboardButton("DexScreener", url=dex_url)],
                [InlineKeyboardButton(get_text('btn_chart', lang), callback_data="action_chart")],
                [InlineKeyboardButton("Set Alarm \u2666\ufe0f", callback_data="action_alarm")],
                [InlineKeyboardButton("Whale Alert \u2663\ufe0f", callback_data="action_whale")],
                [InlineKeyboardButton("Add to Watchlist \u2665\ufe0f", callback_data="watchlist_add")],
                [InlineKeyboardButton("New Analysis \U0001f0cf", callback_data="start_analyzing")],
                [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
            ]
            reply_markup = InlineKeyboardMarkup(kb)

            context.user_data["current_token_data"] = token_data

            if len(report) > 4000:
                parts = [report[i:i+4000] for i in range(0, len(report), 4000)]
                await query.edit_message_text(parts[0], disable_web_page_preview=True)
                for part in parts[1:]:
                    await context.bot.send_message(chat_id=query.from_user.id, text=part, disable_web_page_preview=True)
                await context.bot.send_message(chat_id=query.from_user.id, text="Analysis complete.", reply_markup=reply_markup, disable_web_page_preview=True)
            else:
                await query.edit_message_text(report, reply_markup=reply_markup, disable_web_page_preview=True)

        except Exception as e:
            logger.error(f"Analysis error: {e}")
            await query.edit_message_text(f"❌ Error during analysis: {str(e)[:200]}")

    # ===== ADVANCED CHART =====
    elif query.data == "action_chart":
        # Charts require premium
        paywall = _check_premium_only(user_id, "Advanced Charts")
        if paywall:
            kb = [
                [InlineKeyboardButton("Upgrade Premium - from $18.49", callback_data="buy_premium")],
                [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
            ]
            await query.edit_message_text(paywall, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return

        token_data = context.user_data.get("current_token_data")
        token_address = context.user_data.get("current_token_address")

        if not token_data or not token_address:
            await query.edit_message_text("⚠️ Token data not found. Please run analysis first.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Main Menu", callback_data="home")]]))
            return

        await query.edit_message_text("📊 Generating chart...", disable_web_page_preview=True)

        try:
            chart_buf = generate_price_chart(token_data)
            if chart_buf:
                token_symbol = context.user_data.get("current_token_symbol", "???")
                token_name = context.user_data.get("current_token_name", "Unknown")

                kb = [
                    [InlineKeyboardButton("Start Analysis \u2666\ufe0f", callback_data="action_analysis")],
                    [InlineKeyboardButton("Set Alarm \u2666\ufe0f", callback_data="action_alarm")],
                    [InlineKeyboardButton("Whale Alert \u2663\ufe0f", callback_data="action_whale")],
                    [InlineKeyboardButton("New Analysis \U0001f0cf", callback_data="start_analyzing")],
                    [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
                ]

                await context.bot.send_photo(
                    chat_id=query.from_user.id,
                    photo=chart_buf,
                    caption=f"📊 {token_name} (${token_symbol}) — 24h Price Chart\n\nPowered by kodarkweb3 | @yms56",
                    reply_markup=InlineKeyboardMarkup(kb),
                )
                try:
                    await query.delete_message()
                except Exception:
                    pass
            else:
                await query.edit_message_text(
                    "⚠️ Could not generate chart. Insufficient price data.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Main Menu", callback_data="home")]]),
                    disable_web_page_preview=True,
                )
        except Exception as e:
            logger.error(f"Chart generation error: {e}")
            await query.edit_message_text(f"❌ Chart error: {str(e)[:200]}")

    # ===== SET PRICE ALARM =====
    elif query.data == "action_alarm":
        # Check alarm access (free tier or premium)
        paywall = _check_alarm_access(user_id, lang)
        if paywall:
            kb = [
                [InlineKeyboardButton("Upgrade Premium - from $18.49", callback_data="buy_premium")],
                [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
            ]
            await query.edit_message_text(paywall, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return

        token_address = context.user_data.get("current_token_address")
        token_name = context.user_data.get("current_token_name", "Unknown")
        token_symbol = context.user_data.get("current_token_symbol", "???")

        if not token_address:
            await query.edit_message_text("⚠️ Token address lost. Please start again.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Main Menu", callback_data="home")]]))
            return

        kb = [
            [InlineKeyboardButton("Price Goes Above \u2660\ufe0f", callback_data="alarm_price_above")],
            [InlineKeyboardButton("Price Goes Below \u2666\ufe0f", callback_data="alarm_price_below")],
            [InlineKeyboardButton("% Price Increase \u2663\ufe0f", callback_data="alarm_pct_up")],
            [InlineKeyboardButton("% Price Decrease \u2665\ufe0f", callback_data="alarm_pct_down")],
            [InlineKeyboardButton(get_text('btn_back', lang), callback_data="token_actions")],
        ]

        current_price = context.user_data.get("current_token_price", "N/A")
        premium = get_user_premium_status(user_id)
        usage_hint = ""
        if not premium["is_premium"]:
            usage = get_free_usage(user_id)
            usage_hint = f"\n🆓 Free alarms remaining: {usage['alarms_left']}/{FREE_ALARM_LIMIT}\n"

        await query.edit_message_text(
            f"⏰ SET PRICE ALARM\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"Token: ${token_symbol} ({token_name})\n"
            f"Current Price: ${current_price}\n"
            f"{usage_hint}\n"
            f"Choose alarm type:",
            reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
        )

    elif query.data in ("alarm_price_above", "alarm_price_below", "alarm_pct_up", "alarm_pct_down"):
        alarm_type_map = {
            "alarm_price_above": ("price_above", "Enter target price (e.g., 0.0025):"),
            "alarm_price_below": ("price_below", "Enter target price (e.g., 0.0010):"),
            "alarm_pct_up": ("pct_up", "Enter percentage increase (e.g., 50 for 50%):"),
            "alarm_pct_down": ("pct_down", "Enter percentage decrease (e.g., 30 for 30%):"),
        }
        alarm_type, prompt = alarm_type_map[query.data]
        context.user_data["setting_alarm_type"] = alarm_type
        context.user_data["waiting_for_alarm_value"] = True

        await query.edit_message_text(
            f"⏰ {prompt}\n\nType the value below:",
            disable_web_page_preview=True,
        )

    # ===== WHALE ALERT =====
    elif query.data == "action_whale":
        # Whale alerts are premium-only
        paywall = _check_premium_only(user_id, "Whale Alerts")
        if paywall:
            kb = [
                [InlineKeyboardButton("Upgrade Premium - from $18.49", callback_data="buy_premium")],
                [InlineKeyboardButton(get_text('btn_back', lang), callback_data="token_actions")],
                [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
            ]
            await query.edit_message_text(paywall, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return

        token_address = context.user_data.get("current_token_address")
        token_name = context.user_data.get("current_token_name", "Unknown")
        token_symbol = context.user_data.get("current_token_symbol", "???")

        if not token_address:
            await query.edit_message_text("⚠️ Token address lost. Please start again.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Main Menu", callback_data="home")]]))
            return

        result = add_whale_alert(user_id, token_address, token_name, token_symbol)

        if "error" in result:
            kb = [[InlineKeyboardButton(get_text('btn_back', lang), callback_data="token_actions")], [InlineKeyboardButton("Main Menu", callback_data="home")]]
            await query.edit_message_text(f"⚠️ {result['error']}", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
        else:
            kb = [
                [InlineKeyboardButton("My Whale Alerts \u2663\ufe0f", callback_data="my_whale_alerts")],
                [InlineKeyboardButton("New Analysis \U0001f0cf", callback_data="start_analyzing")],
                [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
            ]
            await query.edit_message_text(
                f"✅ Whale Alert Activated!\n\n"
                f"🐋 Tracking: ${token_symbol} ({token_name})\n\n"
                f"You will receive notifications when whale activity is detected:\n"
                f"• Large volume spikes\n"
                f"• Sharp price movements\n"
                f"• Buy/sell imbalances\n"
                f"• Large trade sizes\n\n"
                f"Monitoring runs every 3 minutes.",
                reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
            )

    # ===== TOKEN ACTIONS (back to choices) =====
    elif query.data == "token_actions":
        token_symbol = context.user_data.get("current_token_symbol", "???")
        token_name = context.user_data.get("current_token_name", "Unknown")
        token_price = context.user_data.get("current_token_price", "N/A")

        kb = [
            [InlineKeyboardButton("Start Analysis \u2666\ufe0f", callback_data="action_analysis")],
            [InlineKeyboardButton(get_text('btn_chart', lang), callback_data="action_chart")],
            [InlineKeyboardButton("Set Price Alarm \u2666\ufe0f", callback_data="action_alarm")],
            [InlineKeyboardButton("Whale Alert \u2663\ufe0f", callback_data="action_whale")],
            [InlineKeyboardButton("Add to Watchlist \u2665\ufe0f", callback_data="watchlist_add")],
            [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
        ]
        await query.edit_message_text(
            f"TOKEN: ${token_symbol} ({token_name}) \U0001f0cf\n"
            f"Price: ${token_price}\n\n"
            f"Select an action \U0001f0cf",
            reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
        )

    # ===== MY ALARMS =====
    elif query.data == "my_alarms":
        alarms = get_user_alarms(user_id)
        if not alarms:
            kb = [
                [InlineKeyboardButton("START ANALYZING \U0001f0cf", callback_data="start_analyzing")],
                [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
            ]
            await query.edit_message_text("MY ALARMS \u2666\ufe0f\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\nNo active alarms.\n\nTo set an alarm, analyze a token first.", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
        else:
            text = "MY ALARMS \u2666\ufe0f\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            for a in alarms:
                text += f"#{a['id']} {format_alarm_text(a)}\n"
            text += f"\nTotal: {len(alarms)} active alarm(s)"

            kb = [
                [InlineKeyboardButton("Delete All Alarms", callback_data="delete_all_alarms")],
                [InlineKeyboardButton("Refresh", callback_data="my_alarms")],
                [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    elif query.data == "delete_all_alarms":
        count = delete_all_alarms(user_id)
        kb = [[InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")]]
        await query.edit_message_text(f"🗑 Deleted {count} alarm(s).", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    # ===== MY WHALE ALERTS =====
    elif query.data == "my_whale_alerts":
        # Whale alerts are premium-only
        paywall = _check_premium_only(user_id, "Whale Alerts")
        if paywall:
            kb = [
                [InlineKeyboardButton("Upgrade Premium - from $18.49", callback_data="buy_premium")],
                [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
            ]
            await query.edit_message_text(paywall, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return

        alerts = get_user_whale_alerts(user_id)
        if not alerts:
            kb = [
                [InlineKeyboardButton("START ANALYZING \U0001f0cf", callback_data="start_analyzing")],
                [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
            ]
            await query.edit_message_text("MY WHALE ALERTS \u2663\ufe0f\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\nNo active whale alerts.\n\nTo set a whale alert, analyze a token first.", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
        else:
            text = "MY WHALE ALERTS \u2663\ufe0f\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            for a in alerts:
                text += f"#{a['id']} ${a['token_symbol']} — {a['token_name']}\n"
            text += f"\nTotal: {len(alerts)} active whale alert(s)\nChecking every 3 minutes."

            kb = [
                [InlineKeyboardButton("Delete All Whale Alerts", callback_data="delete_all_whale_alerts")],
                [InlineKeyboardButton("Refresh", callback_data="my_whale_alerts")],
                [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    elif query.data == "delete_all_whale_alerts":
        count = delete_all_whale_alerts(user_id)
        kb = [[InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")]]
        await query.edit_message_text(f"🗑 Deleted {count} whale alert(s).", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    # ===== SNIPER ALERTS MENU =====
    elif query.data == "sniper_menu":
        # Sniper alerts are premium-only
        paywall = _check_premium_only(user_id, "Auto-Sniper Alerts")
        if paywall:
            kb = [
                [InlineKeyboardButton("Upgrade Premium - from $18.49", callback_data="buy_premium")],
                [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
            ]
            await query.edit_message_text(paywall, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return

        status = get_user_sniper_status(user_id)
        active_platforms = status.get("platforms", [])

        if status["active"] and active_platforms:
            plat_names = []
            for p in active_platforms:
                plat_names.append(f"{get_platform_emoji(p)} {PLATFORM_OPTIONS.get(p, p)}")
            plat_text = "\n".join(plat_names)
            status_text = f"✅ Auto-Sniper: ACTIVE\n\n📡 Monitoring:\n{plat_text}"
        else:
            status_text = "❌ Auto-Sniper: INACTIVE\n\nSubscribe to get alerts when new tokens launch."

        kb = [
            [InlineKeyboardButton("🌐 All Platforms", callback_data="sniper_sub_all")],
            [InlineKeyboardButton("🎰 Pump.fun", callback_data="sniper_sub_pump_fun")],
            [InlineKeyboardButton("💧 Raydium", callback_data="sniper_sub_raydium")],
            [InlineKeyboardButton("🪐 Jupiter", callback_data="sniper_sub_jupiter")],
        ]
        if status["active"]:
            kb.append([InlineKeyboardButton("🔴 Unsubscribe All", callback_data="sniper_unsub_all")])
        kb.append([InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")])

        await query.edit_message_text(
            f"{get_text('sniper_title', lang)}\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"{get_text('sniper_desc', lang)}\n\n"
            f"{status_text}\n\n"
            f"Choose a platform to monitor:",
            reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
        )

    elif query.data.startswith("sniper_sub_"):
        platform = query.data.replace("sniper_sub_", "")
        result = subscribe_sniper(user_id, platform)

        if result["success"]:
            plat_name = PLATFORM_OPTIONS.get(platform, platform)
            kb = [
                [InlineKeyboardButton("🎯 Sniper Settings", callback_data="sniper_menu")],
                [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
            ]
            await query.edit_message_text(
                f"✅ Subscribed to {plat_name}!\n\n"
                f"You will receive alerts when new tokens are detected.\n"
                f"Monitoring runs every 5 minutes.\n\n"
                f"📡 Active platforms: {', '.join(result['platforms'])}",
                reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
            )

    elif query.data == "sniper_unsub_all":
        unsubscribe_sniper(user_id, "all")
        kb = [
            [InlineKeyboardButton("🎯 Sniper Settings", callback_data="sniper_menu")],
            [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
        ]
        await query.edit_message_text(
            "🔴 Unsubscribed from all sniper alerts.\n\n"
            "You will no longer receive new token notifications.",
            reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
        )

    # ===== SIGNALS =====
    elif query.data == "signals":
        # Market signals are premium-only
        paywall = _check_premium_only(user_id, "Market Signals")
        if paywall:
            kb = [
                [InlineKeyboardButton("Upgrade Premium - from $18.49", callback_data="buy_premium")],
                [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
            ]
            await query.edit_message_text(paywall, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return
        await query.edit_message_text("⏳ Loading market data...", disable_web_page_preview=True)
        await _send_signals(query.message, user_id)

    # ===== PREMIUM =====
    elif query.data == "premium":
        premium = get_user_premium_status(user_id)
        text = _build_premium_text(premium, user_id)
        kb = _build_premium_keyboard(premium)
        await query.edit_message_text(text, reply_markup=kb, disable_web_page_preview=True)

    elif query.data == "buy_premium":
        # Legacy callback - redirect to plan selection
        premium = get_user_premium_status(user_id)
        text = _build_premium_text(premium, user_id)
        kb = _build_premium_keyboard(premium)
        await query.edit_message_text(text, reply_markup=kb, disable_web_page_preview=True)

    elif query.data == "select_plan":
        premium = get_user_premium_status(user_id)
        text = _build_premium_text(premium, user_id)
        kb = _build_premium_keyboard(premium)
        await query.edit_message_text(text, reply_markup=kb, disable_web_page_preview=True)

    elif query.data == "pay_sol_select":
        sol_price = _get_sol_price_usd()
        if sol_price <= 0:
            await query.answer("Could not fetch SOL price. Try again.", show_alert=True)
            return
        text = (
            f"PAY WITH SOL \u2660\ufe0f\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            f"Current SOL price: ${sol_price:.2f}\n\n"
            f"Select your plan:\n\n"
        )
        campaign_note = ""
        if CAMPAIGN_BUY1_GET1:
            campaign_note = " (+1 Month FREE)"
        for key, plan in PREMIUM_PLANS.items():
            sol_amount = round(plan["price_usd"] / sol_price, 4)
            bonus = campaign_note if key == "1_month" else ""
            text += f"{plan['label']}: {sol_amount} SOL (${plan['price_usd']}){bonus}\n"
        text += f"\nNo commission. 100% goes to the developer.\nSelect a plan:"
        kb = []
        for key, plan in PREMIUM_PLANS.items():
            sol_amount = round(plan["price_usd"] / sol_price, 4)
            bonus = " +1 FREE" if CAMPAIGN_BUY1_GET1 and key == "1_month" else ""
            kb.append([InlineKeyboardButton(f"{plan['label']} - {sol_amount} SOL{bonus}", callback_data=f"sol_pay_{key}")])
        kb.append([InlineKeyboardButton("Back", callback_data="premium")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    elif query.data == "pay_stars_select":
        text = (
            f"PAY WITH TELEGRAM STARS \u2666\ufe0f\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            f"Select your plan:\n\n"
        )
        for key, plan in PREMIUM_PLANS.items():
            text += f"{plan['label']}: {plan['stars']} Stars (~${plan['stars'] * 0.017:.2f})\n"
        text += f"\nPay securely via Telegram.\nSelect a plan:"
        kb = []
        for key, plan in PREMIUM_PLANS.items():
            kb.append([InlineKeyboardButton(f"{plan['label']} - {plan['stars']} Stars", callback_data=f"stars_pay_{key}")])
        kb.append([InlineKeyboardButton("Back", callback_data="premium")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    elif query.data.startswith("stars_pay_"):
        plan_key = query.data.replace("stars_pay_", "")
        await send_premium_invoice(query, context, plan_key=plan_key)

    elif query.data.startswith("sol_pay_"):
        plan_key = query.data.replace("sol_pay_", "")
        plan = PREMIUM_PLANS.get(plan_key)
        if not plan:
            await query.answer("Invalid plan.", show_alert=True)
            return
        sol_price = _get_sol_price_usd()
        if sol_price <= 0:
            await query.answer("Could not fetch SOL price. Try again.", show_alert=True)
            return
        sol_amount = round(plan["price_usd"] / sol_price, 4)
        memo = _generate_payment_memo(user_id)

        # Save pending payment
        data = load_user_data()
        user_str = str(user_id)
        if user_str not in data:
            data[user_str] = _new_user_record()
        data[user_str]["pending_sol_payment"] = {
            "plan": plan_key,
            "amount_sol": sol_amount,
            "price_usd": plan["price_usd"],
            "created": datetime.now().isoformat(),
            "memo": memo,
            "verified": False,
        }
        save_user_data(data)

        campaign_note = ""
        if CAMPAIGN_BUY1_GET1 and plan_key == "1_month":
            campaign_note = "\n\n\U0001f0cf BONUS: You will receive 60 days (1+1 campaign active)"

        text = (
            f"SOL PAYMENT \u2660\ufe0f\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            f"Plan: {plan['label']}\n"
            f"Amount: {sol_amount} SOL (${plan['price_usd']})\n\n"
            f"Send exactly {sol_amount} SOL to:\n\n"
            f"`{SOL_WALLET_ADDRESS}`\n\n"
            f"(Tap to copy)\n\n"
            f"Payment ID: {memo}\n"
            f"{campaign_note}\n\n"
            f"After sending, tap 'Verify Payment' below.\n"
            f"The bot will automatically check the blockchain.\n\n"
            f"Payment valid for 30 minutes."
        )
        kb = [
            [InlineKeyboardButton("Verify Payment \u2705", callback_data=f"verify_sol_{memo}")],
            [InlineKeyboardButton("Cancel", callback_data="premium")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown", disable_web_page_preview=True)

    elif query.data.startswith("verify_sol_"):
        memo = query.data.replace("verify_sol_", "")
        data = load_user_data()
        user_str = str(user_id)
        pending = data.get(user_str, {}).get("pending_sol_payment")

        if not pending or pending.get("memo") != memo:
            await query.answer("No pending payment found.", show_alert=True)
            return

        if pending.get("verified"):
            await query.answer("This payment was already verified.", show_alert=True)
            return

        # Check if payment expired (30 min)
        created = datetime.fromisoformat(pending["created"])
        if (datetime.now() - created).total_seconds() > 1800:
            data[user_str]["pending_sol_payment"] = None
            save_user_data(data)
            await query.answer("Payment expired. Please start a new payment.", show_alert=True)
            return

        await query.answer("Checking blockchain... Please wait.", show_alert=False)

        # Verify on blockchain
        verified = await _verify_sol_payment(
            SOL_WALLET_ADDRESS,
            pending["amount_sol"],
            pending["memo"],
            pending["created"]
        )

        if verified:
            plan_key = pending["plan"]
            plan = PREMIUM_PLANS.get(plan_key, PREMIUM_PLANS["1_month"])
            days = plan["days"]

            # Apply campaign bonus
            if CAMPAIGN_BUY1_GET1 and plan_key == "1_month":
                days = 60

            until = activate_premium(user_id, days=days)
            data[user_str]["paid_premium"] = True
            data[user_str]["pending_sol_payment"] = None
            save_user_data(data)

            username = update.effective_user.username or update.effective_user.first_name or "Unknown"
            record_user_activity(user_id, username, "sol_payment")
            date_str = until.strftime('%d.%m.%Y %H:%M')

            bonus_text = ""
            if CAMPAIGN_BUY1_GET1 and plan_key == "1_month":
                bonus_text = "\n\U0001f0cf Campaign Bonus: +30 days FREE applied!"

            kb = [
                [InlineKeyboardButton("START ANALYZING \U0001f0cf", callback_data="start_analyzing")],
                [InlineKeyboardButton("Main Menu", callback_data="home")],
            ]
            await query.edit_message_text(
                f"Payment Verified \u2705\n\n"
                f"Your {days}-day Premium subscription is now active!\n"
                f"Expires: {date_str}\n"
                f"{bonus_text}\n\n"
                f"All premium features are unlocked.\n"
                f"Thank you for your support!",
                reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
            )
        else:
            kb = [
                [InlineKeyboardButton("Verify Payment \u2705", callback_data=f"verify_sol_{memo}")],
                [InlineKeyboardButton("Cancel", callback_data="premium")],
            ]
            await query.edit_message_text(
                f"Payment not found yet.\n\n"
                f"If you already sent {pending['amount_sol']} SOL to:\n"
                f"`{SOL_WALLET_ADDRESS}`\n\n"
                f"Please wait 1-2 minutes for blockchain confirmation,\n"
                f"then tap 'Verify Payment' again.\n\n"
                f"Payment ID: {memo}",
                reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown", disable_web_page_preview=True,
            )

    # ===== FEEDBACK =====
    elif query.data == "feedback_start":
        context.user_data["waiting_for_feedback"] = True
        await query.edit_message_text(
            "💬 FEEDBACK\n"
            "━━━━━━━━━━━━━━━\n\n"
            "We value your feedback!\n\n"
            "Please type your feedback, suggestion, or bug report below.\n"
            "Your message will be sent to the kodark.io team.\n\n"
            "Type your message:",
            disable_web_page_preview=True,
        )

    # ===== TRENDING TOP 10 =====
    elif query.data == "trending_tokens":
        await query.edit_message_text("⏳ Loading trending tokens...", disable_web_page_preview=True)
        try:
            trending_data = await _fetch_trending_tokens()
            if not trending_data:
                kb = [[InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")]]
                await query.edit_message_text("⚠️ Could not fetch trending data. Try again later.", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
                return
            
            text = "♦️ TRENDING TOP 10 — Solana\n━━━━━━━━━━━━━━━\n\n"
            for i, token in enumerate(trending_data[:10], 1):
                symbol = token.get("symbol", "???")
                name = token.get("name", "Unknown")[:20]
                price = token.get("price", 0)
                change_24h = token.get("change_24h", 0)
                volume = token.get("volume_24h", 0)
                
                arrow = "▲" if change_24h >= 0 else "▼"
                change_str = f"{arrow} {abs(change_24h):.1f}%"
                
                if volume >= 1_000_000:
                    vol_str = f"${volume/1_000_000:.1f}M"
                elif volume >= 1_000:
                    vol_str = f"${volume/1_000:.0f}K"
                else:
                    vol_str = f"${volume:.0f}"
                
                if price >= 0.01:
                    price_str = f"${price:.4f}"
                else:
                    price_str = f"${price:.8f}"
                
                text += f"{i}. {symbol} — {name}\n"
                text += f"   {price_str} | {change_str} | Vol: {vol_str}\n\n"
            
            text += "Data from DexScreener \u2660️"
            
            kb = [
                [InlineKeyboardButton("Refresh", callback_data="trending_tokens")],
                [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Trending error: {e}")
            kb = [[InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")]]
            await query.edit_message_text("⚠️ Error loading trending data.", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    # ===== WATCHLIST =====
    elif query.data == "watchlist_menu":
        data = load_user_data()
        user_str = str(user_id)
        watchlist = data.get(user_str, {}).get("watchlist", [])
        
        if not watchlist:
            kb = [
                [InlineKeyboardButton("START ANALYZING \U0001f0cf", callback_data="start_analyzing")],
                [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
            ]
            await query.edit_message_text(
                "MY WATCHLIST \u2665\ufe0f\n"
                "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
                "Your watchlist is empty.\n\n"
                "Analyze a token first, then add it to your watchlist from the token actions menu.\n\n"
                "Start analyzing to build your list \U0001f0cf",
                reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
            )
        else:
            text = "MY WATCHLIST \u2665\ufe0f\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            for i, token in enumerate(watchlist, 1):
                text += f"{i}. ${token['symbol']} — {token['name']}\n"
                text += f"   {token['address'][:8]}...{token['address'][-6:]}\n\n"
            text += f"Total: {len(watchlist)} token(s) \u2663️"
            kb = []
            for token in watchlist:
                kb.append([InlineKeyboardButton(f"🔍 ${token['symbol']}", callback_data=f"wl_analyze_{token['address']}")])
            kb.append([InlineKeyboardButton("🗑 Clear Watchlist", callback_data="watchlist_clear")])
            kb.append([InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")])
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    elif query.data == "watchlist_clear":
        data = load_user_data()
        user_str = str(user_id)
        if user_str in data:
            data[user_str]["watchlist"] = []
            save_user_data(data)
        kb = [[InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")]]
        await query.edit_message_text("🗑 Watchlist cleared.", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    elif query.data.startswith("wl_analyze_"):
        token_address = query.data.replace("wl_analyze_", "")
        context.user_data["current_token_address"] = token_address
        context.user_data["waiting_for_address"] = False
        await query.edit_message_text("⏳ Fetching token data...", disable_web_page_preview=True)
        # Trigger analysis
        token_data = await get_token_info(token_address)
        if not token_data or "error" in token_data:
            kb = [[InlineKeyboardButton("My Watchlist \u2665\ufe0f", callback_data="watchlist_menu")], [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")]]
            await query.edit_message_text(f"⚠️ Could not fetch token data. Try again later.", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return
        token_name = token_data.get("name", "Unknown")
        token_symbol = token_data.get("symbol", "???")
        token_price = token_data.get("price_usd", "N/A")
        context.user_data["current_token_data"] = token_data
        kb = [
            [InlineKeyboardButton("Full Analysis \U0001f0cf", callback_data="action_analyze")],
            [InlineKeyboardButton("Price Chart", callback_data="action_chart")],
            [InlineKeyboardButton("Set Price Alarm \u2666\ufe0f", callback_data="action_alarm")],
            [InlineKeyboardButton("Whale Alert \u2663\ufe0f", callback_data="action_whale")],
            [InlineKeyboardButton("My Watchlist \u2665\ufe0f", callback_data="watchlist_menu")],
            [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
        ]
        await query.edit_message_text(
            f"TOKEN: ${token_symbol} ({token_name}) \U0001f0cf\n"
            f"Price: ${token_price}\n\n"
            f"Select an action \U0001f0cf",
            reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
        )

    elif query.data == "watchlist_add":
        token_address = context.user_data.get("current_token_address")
        token_data = context.user_data.get("current_token_data", {})
        if not token_address:
            kb = [[InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")]]
            await query.edit_message_text("⚠️ No token selected.", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return
        
        data = load_user_data()
        user_str = str(user_id)
        if user_str not in data:
            data[user_str] = _new_user_record()
        
        watchlist = data[user_str].get("watchlist", [])
        
        # Check if already in watchlist
        if any(t["address"] == token_address for t in watchlist):
            kb = [[InlineKeyboardButton("My Watchlist \u2665\ufe0f", callback_data="watchlist_menu")], [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")]]
            await query.edit_message_text("⚠️ Token already in your watchlist.", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return
        
        # Max 10 tokens in watchlist
        if len(watchlist) >= 10:
            kb = [[InlineKeyboardButton("My Watchlist \u2665\ufe0f", callback_data="watchlist_menu")], [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")]]
            await query.edit_message_text("⚠️ Watchlist full (max 10 tokens).", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return
        
        watchlist.append({
            "address": token_address,
            "symbol": token_data.get("symbol", "???"),
            "name": token_data.get("name", "Unknown"),
            "added": datetime.now().isoformat(),
        })
        data[user_str]["watchlist"] = watchlist
        save_user_data(data)
        
        kb = [
            [InlineKeyboardButton("My Watchlist \u2665\ufe0f", callback_data="watchlist_menu")],
            [InlineKeyboardButton("New Analysis \U0001f0cf", callback_data="start_analyzing")],
            [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
        ]
        await query.edit_message_text(
            f"✅ Added ${token_data.get('symbol', '???')} to your watchlist \u2665️\n\n"
            f"You now have {len(watchlist)} token(s) in your watchlist.",
            reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
        )

    # ===== ALERTS HUB =====
    elif query.data == "alerts_hub":
        kb = [
            [InlineKeyboardButton("My Price Alarms \u2666\ufe0f", callback_data="my_alarms")],
            [InlineKeyboardButton("My Whale Alerts \u2663\ufe0f", callback_data="my_whale_alerts")],
            [InlineKeyboardButton("Sniper Alerts \u2665\ufe0f", callback_data="sniper_menu")],
            [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
        ]
        await query.edit_message_text(
            "ALERTS HUB \u2663\ufe0f\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            "Manage all your alerts in one place.\n\n"
            "Price Alarms \u2014 Set targets and get notified when price hits your level \u2666\ufe0f\n"
            "Whale Alerts \u2014 Detect large wallet movements on any token \u2663\ufe0f\n"
            "Sniper Alerts \u2014 New token launch notifications from Pump.fun, Raydium, Jupiter \u2665\ufe0f\n\n"
            "Select an alert type below \U0001f0cf",
            reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
        )

    # ===== ROADMAP =====
    elif query.data == "roadmap":
        kb = [[InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")]]
        await query.edit_message_text(
            "🗺 ROADMAP — kodark.io\n"
            "━━━━━━━━━━━━━━━\n\n"
            "✅ COMPLETED\n\n"
            "🐋 Whale Alert Notifications ✅\n"
            "Real-time push alerts when whales buy or sell.\n\n"
            "⏰ Price Alarm System ✅\n"
            "Set custom price targets and get notified.\n\n"
            "🎯 Auto-Sniper Alerts ✅\n"
            "Get notified about new token launches on Pump.fun, Raydium & Jupiter.\n\n"
            "🌐 Multi-Language Support ✅\n"
            "Full support for 15 languages including Turkish, Spanish, Chinese and more.\n\n"
            "📊 Advanced Charting ✅\n"
            "Professional price charts inside Telegram.\n\n"
            "🆓 Free Tier System ✅\n"
            f"{FREE_ANALYSIS_LIMIT} free analyses + {FREE_ALARM_LIMIT} free alarms for new users.\n\n"
            "\U0001f4ac Feedback System \u2705\n"
            "Send feedback directly to the team.\n\n"
            "\U0001f50d Smart Money Wallet Tracker \u2705\n"
            "Track profitable wallets and get instant trade alerts.\n\n"
            "\U0001f4ca Daily Market Summary \u2705\n"
            "Automated daily market overview for premium users.\n\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            "\U0001f51c COMING SOON\n\n"
            "\U0001f465 Referral System\n"
            "Invite friends and earn free premium days.\n\n"
            "\U0001f916 AI Trading Signals\n"
            "Machine learning-based buy/sell signals.\n\n"
            "\U0001f4f1 Mini App Dashboard\n"
            "Full-featured Telegram Mini App with interactive charts.\n\n"
            "\U0001f517 Pump.fun Graduation Radar\n"
            "Get alerted when tokens are about to graduate to Raydium.\n\n"
            "\U0001f3c6 Leaderboard & Community\n"
            "Top traders ranking and community insights.\n\n"
            "Stay tuned for updates!\n\n"
            "🔗 x.com/kodarkweb3\n"
            "🔗 x.com/kodarkio",
            reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
        )

    # ===== ADMIN CALLBACKS =====
    elif query.data == "admin_refresh":
        if user_id != ADMIN_USER_ID:
            return
        stats = get_admin_stats()
        await query.edit_message_text(_build_admin_panel_text(stats), reply_markup=_build_admin_keyboard(stats), disable_web_page_preview=True)

    elif query.data == "admin_users":
        if user_id != ADMIN_USER_ID:
            return
        stats = get_admin_stats()
        kb = [
            [InlineKeyboardButton("Refresh", callback_data="admin_users")],
            [InlineKeyboardButton("◀️ Back to Panel", callback_data="admin_refresh")],
        ]
        await query.edit_message_text(_build_recent_users_text(stats), reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    elif query.data == "admin_premium_list":
        if user_id != ADMIN_USER_ID:
            return
        stats = get_admin_stats()
        kb = [
            [InlineKeyboardButton("Refresh", callback_data="admin_premium_list")],
            [InlineKeyboardButton("◀️ Back to Panel", callback_data="admin_refresh")],
        ]
        await query.edit_message_text(_build_premium_users_text(stats), reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    elif query.data == "admin_analytics":
        if user_id != ADMIN_USER_ID:
            return
        kb = [
            [InlineKeyboardButton("Refresh", callback_data="admin_analytics")],
            [InlineKeyboardButton("◀️ Back to Panel", callback_data="admin_refresh")],
        ]
        await query.edit_message_text(_build_analytics_text(), reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    elif query.data == "admin_feedback":
        if user_id != ADMIN_USER_ID:
            return
        kb = [
            [InlineKeyboardButton("Refresh", callback_data="admin_feedback")],
            [InlineKeyboardButton("◀️ Back to Panel", callback_data="admin_refresh")],
        ]
        await query.edit_message_text(_build_feedback_text(), reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    elif query.data == "admin_campaign":
        if user_id != ADMIN_USER_ID:
            return
        status_icon = "\U0001f7e2" if CAMPAIGN_BUY1_GET1 else "\U0001f534"
        status_text = "ACTIVE" if CAMPAIGN_BUY1_GET1 else "INACTIVE"
        toggle_btn_text = "\u274c Deactivate Campaign" if CAMPAIGN_BUY1_GET1 else "\u2705 Activate Campaign"
        text = (
            f"\U0001f0cf CAMPAIGN MANAGEMENT\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            f"Campaign: Buy 1 Month, Get 1 Month FREE\n\n"
            f"Status: {status_icon} {status_text}\n\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"Details:\n"
            f"  Applies to: SOL payments only\n"
            f"  Plan: 1 Month (pay 30 days, get 60 days)\n"
            f"  Stars payments: NOT affected\n\n"
            f"When active, users who pay 1 month\n"
            f"with SOL receive an extra 30 days free.\n"
            f"This is shown on the /start screen\n"
            f"and payment pages."
        )
        kb = [
            [InlineKeyboardButton(toggle_btn_text, callback_data="admin_toggle_campaign")],
            [InlineKeyboardButton("\u25c0\ufe0f Back to Panel", callback_data="admin_refresh")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    elif query.data == "admin_toggle_campaign":
        if user_id != ADMIN_USER_ID:
            return
        CAMPAIGN_BUY1_GET1 = not CAMPAIGN_BUY1_GET1
        status = "ON \u2705" if CAMPAIGN_BUY1_GET1 else "OFF \u274c"
        # Save to persistent data
        data = load_user_data()
        data["__campaign_buy1_get1"] = CAMPAIGN_BUY1_GET1
        save_user_data(data)
        await query.answer(f"Campaign 1+1 is now {status}", show_alert=True)
        # Refresh campaign page
        status_icon = "\U0001f7e2" if CAMPAIGN_BUY1_GET1 else "\U0001f534"
        status_text = "ACTIVE" if CAMPAIGN_BUY1_GET1 else "INACTIVE"
        toggle_btn_text = "\u274c Deactivate Campaign" if CAMPAIGN_BUY1_GET1 else "\u2705 Activate Campaign"
        text = (
            f"\U0001f0cf CAMPAIGN MANAGEMENT\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            f"Campaign: Buy 1 Month, Get 1 Month FREE\n\n"
            f"Status: {status_icon} {status_text}\n\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"Details:\n"
            f"  Applies to: SOL payments only\n"
            f"  Plan: 1 Month (pay 30 days, get 60 days)\n"
            f"  Stars payments: NOT affected\n\n"
            f"When active, users who pay 1 month\n"
            f"with SOL receive an extra 30 days free.\n"
            f"This is shown on the /start screen\n"
            f"and payment pages."
        )
        kb = [
            [InlineKeyboardButton(toggle_btn_text, callback_data="admin_toggle_campaign")],
            [InlineKeyboardButton("\u25c0\ufe0f Back to Panel", callback_data="admin_refresh")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    elif query.data == "admin_gift_premium":
        if user_id != ADMIN_USER_ID:
            return
        context.user_data["waiting_for_gift_premium_id"] = True
        kb = [[InlineKeyboardButton("❌ İptal", callback_data="admin_refresh")]]
        await query.edit_message_text(
            "🎁 PREMİUM HEDİYE ET\n"
            "━━━━━━━━━━━━━━━\n\n"
            "Kullanıcıya 30 gün ücretsiz premium hediye edebilirsiniz.\n\n"
            "📝 Hediye etmek istediğiniz kullanıcının\n"
            "Telegram ID'sini girin:\n\n"
            "💡 Not: Kullanıcı ID'sini admin panelindeki\n"
            "'Recent Users' veya 'Premium Users' listesinden\n"
            "bulabilirsiniz.",
            reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
        )

    elif query.data == "admin_broadcast_info":
        if user_id != ADMIN_USER_ID:
            return
        kb = [[InlineKeyboardButton("◀️ Back to Panel", callback_data="admin_refresh")]]
        await query.edit_message_text(
            "📢 BROADCAST MESSAGE\n━━━━━━━━━━━━━━━\n\n"
            "Send a broadcast to all users:\n\n"
            "Use the command:\n/broadcast Your message here\n\n"
            "This will send your message to all registered users.",
            reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
        )


    # ===== WALLET TRACKER CALLBACKS =====
    elif query.data == "wallet_tracker_menu":
        paywall = _check_premium_only(user_id, "Smart Money Wallet Tracker")
        if paywall:
            kb = [
                [InlineKeyboardButton("Upgrade Premium - from $18.49", callback_data="buy_premium")],
                [InlineKeyboardButton("Main Menu", callback_data="home")],
            ]
            await query.edit_message_text(paywall, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return

        wallets = get_tracked_wallets(user_id)
        wallet_count = len(wallets)

        text = (
            f"SMART MONEY TRACKER \U0001f0cf\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            f"Track profitable wallets and get instant\n"
            f"notifications when they make trades.\n\n"
            f"Tracked Wallets: {wallet_count}/{MAX_TRACKED_WALLETS_PREMIUM}\n\n"
        )

        if wallets:
            for i, w in enumerate(wallets, 1):
                addr = w['address']
                text += f"{i}. {w['label']}\n   {addr[:6]}...{addr[-4:]}\n\n"

        text += "\U0001f4a1 Tip: Track wallets of successful traders\nto follow their moves in real-time."

        kb = []
        if wallet_count < MAX_TRACKED_WALLETS_PREMIUM:
            kb.append([InlineKeyboardButton("\u2795 Add Wallet", callback_data="wallet_add")])
        if wallets:
            kb.append([InlineKeyboardButton("\U0001f5d1 Remove All", callback_data="wallet_remove_all")])
        kb.append([InlineKeyboardButton("Main Menu", callback_data="home")])

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    elif query.data == "wallet_add":
        context.user_data["waiting_for_wallet_address"] = True
        kb = [[InlineKeyboardButton("\u274c Cancel", callback_data="wallet_tracker_menu")]]
        await query.edit_message_text(
            "\U0001f50d ADD WALLET TO TRACK\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            "Send the Solana wallet address you want to track.\n\n"
            "\U0001f4a1 Tips:\n"
            "\u2022 Find profitable wallets on Solscan\n"
            "\u2022 Copy addresses from DEX leaderboards\n"
            "\u2022 Track known smart money wallets\n\n"
            "\U0001f4e9 Paste the wallet address below:",
            reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
        )

    elif query.data == "wallet_remove_all":
        count = remove_all_tracked_wallets(user_id)
        kb = [[InlineKeyboardButton("\U0001f50d Wallet Tracker", callback_data="wallet_tracker_menu")],
              [InlineKeyboardButton("Main Menu", callback_data="home")]]
        await query.edit_message_text(
            f"\u2705 Removed {count} wallet(s) from tracking.\n\n"
            f"You can add new wallets anytime.",
            reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
        )

    elif query.data.startswith("wallet_remove_"):
        addr = query.data.replace("wallet_remove_", "")
        removed = remove_tracked_wallet(user_id, addr)
        if removed:
            await query.edit_message_text("\u2705 Wallet removed from tracking.")
        else:
            await query.edit_message_text("\u26a0\ufe0f Wallet not found.")
        # Redirect to tracker menu
        wallets = get_tracked_wallets(user_id)
        wallet_count = len(wallets)
        text = f"SMART MONEY TRACKER \U0001f0cf\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\nTracked Wallets: {wallet_count}/{MAX_TRACKED_WALLETS_PREMIUM}\n\n"
        if wallets:
            for i, w in enumerate(wallets, 1):
                a = w['address']
                text += f"{i}. {w['label']}\n   {a[:6]}...{a[-4:]}\n\n"
        kb = []
        if wallet_count < MAX_TRACKED_WALLETS_PREMIUM:
            kb.append([InlineKeyboardButton("\u2795 Add Wallet", callback_data="wallet_add")])
        if wallets:
            kb.append([InlineKeyboardButton("\U0001f5d1 Remove All", callback_data="wallet_remove_all")])
        kb.append([InlineKeyboardButton("Main Menu", callback_data="home")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    # ===== DAILY SUMMARY TOGGLE =====
    elif query.data == "toggle_daily_summary":
        new_state = toggle_daily_summary(user_id)
        state_text = "\u2705 Enabled" if new_state else "\u274c Disabled"
        kb = [[InlineKeyboardButton("Main Menu", callback_data="home")]]
        await query.edit_message_text(
            f"\U0001f4ca Daily Market Summary: {state_text}\n\n"
            f"{'You will receive daily market updates at 09:00 UTC.' if new_state else 'You will no longer receive daily summaries.'}\n\n"
            f"You can change this anytime from the main menu.",
            reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
        )


# ==================== MESSAGE HANDLER ====================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or "Unknown"
    record_user_activity(user_id, username, "message")
    text = update.message.text.strip()
    lang = get_user_lang(user_id)

    # ===== ADMIN: WAITING FOR GIFT PREMIUM USER ID =====
    if context.user_data.get("waiting_for_gift_premium_id"):
        context.user_data["waiting_for_gift_premium_id"] = False

        # Only admin can use this
        if user_id != ADMIN_USER_ID:
            return

        # Parse the Telegram ID
        try:
            target_user_id = int(text.strip())
        except ValueError:
            kb = [[InlineKeyboardButton("🎁 Tekrar Dene", callback_data="admin_gift_premium")],
                  [InlineKeyboardButton("◀️ Admin Panel", callback_data="admin_refresh")]]
            await update.message.reply_text(
                "⚠️ Geçersiz ID! Lütfen sayısal bir Telegram ID girin.",
                reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
            )
            return

        # Activate 30 days premium for the target user
        until = activate_premium(target_user_id, days=30)
        date_str = until.strftime('%d.%m.%Y %H:%M')

        # Log the gift in user data
        data = load_user_data()
        target_str = str(target_user_id)
        if target_str not in data:
            data[target_str] = _new_user_record()
        if "gift_log" not in data[target_str]:
            data[target_str]["gift_log"] = []
        data[target_str]["gift_log"].append({
            "gifted_by": user_id,
            "days": 30,
            "date": datetime.now().isoformat(),
        })
        save_user_data(data)

        target_username = data.get(target_str, {}).get("username", "Bilinmiyor")

        # Notify the target user
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    "🎁 TEBLİKLER! PREMİUM HEDİYE!\n"
                    "━━━━━━━━━━━━━━━\n\n"
                    "✅ Size 30 günlük Premium üyelik hediye edildi!\n\n"
                    f"📅 Bitiş: {date_str}\n\n"
                    "🔓 Tüm premium özellikler aktif:\n"
                    "• Sınırsız token analizi\n"
                    "• Smart Money Wallet Tracker\n"
                    "• Whale Alert bildirimleri\n"
                    "• Auto-Sniper alerts\n"
                    "• Günlük piyasa özeti\n\n"
                    "Keyifli kullanımlar! 🚀\n\n"
                    "— kodark.io Team"
                ),
                disable_web_page_preview=True,
            )
            notify_status = "✅ Kullanıcıya bildirim gönderildi"
        except Exception as e:
            logger.error(f"Gift premium notification error: {e}")
            notify_status = "⚠️ Kullanıcıya bildirim gönderilemedi (bot'u başlatmamış olabilir)"

        # Confirm to admin
        kb = [
            [InlineKeyboardButton("🎁 Başka Birine Hediye Et", callback_data="admin_gift_premium")],
            [InlineKeyboardButton("◀️ Admin Panel", callback_data="admin_refresh")],
        ]
        await update.message.reply_text(
            f"✅ PREMİUM HEDİYE EDİLDİ!\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"👤 Kullanıcı: @{target_username}\n"
            f"🆔 ID: {target_user_id}\n"
            f"📅 Süre: 30 gün\n"
            f"📆 Bitiş: {date_str}\n\n"
            f"{notify_status}",
            reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
        )
        return

    # ===== WAITING FOR WALLET ADDRESS =====
    if context.user_data.get("waiting_for_wallet_address"):
        context.user_data["waiting_for_wallet_address"] = False
        wallet_address = text.strip()

        # Validate Solana address (32-44 chars, base58)
        if len(wallet_address) < 32 or len(wallet_address) > 50:
            kb = [[InlineKeyboardButton("\U0001f50d Wallet Tracker", callback_data="wallet_tracker_menu")],
                  [InlineKeyboardButton("Main Menu", callback_data="home")]]
            await update.message.reply_text(
                "\u26a0\ufe0f Invalid wallet address. Please enter a valid Solana address.",
                reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
            )
            return

        # Check if already tracking
        existing = get_tracked_wallets(user_id)
        for w in existing:
            if w["address"] == wallet_address:
                kb = [[InlineKeyboardButton("\U0001f50d Wallet Tracker", callback_data="wallet_tracker_menu")]]
                await update.message.reply_text(
                    "\u26a0\ufe0f You are already tracking this wallet.",
                    reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
                )
                return

        context.user_data["pending_wallet_address"] = wallet_address
        context.user_data["waiting_for_wallet_label"] = True
        kb = [[InlineKeyboardButton("\u274c Cancel", callback_data="wallet_tracker_menu")]]
        await update.message.reply_text(
            f"\u2705 Address received:\n{wallet_address[:8]}...{wallet_address[-6:]}\n\n"
            f"Now give this wallet a label (e.g. \"Smart Whale 1\", \"Top Trader\"):\n\n"
            f"\U0001f4e9 Type a name below:",
            reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
        )
        return

    # ===== WAITING FOR WALLET LABEL =====
    if context.user_data.get("waiting_for_wallet_label"):
        context.user_data["waiting_for_wallet_label"] = False
        label = text.strip()[:30]  # Max 30 chars
        wallet_address = context.user_data.get("pending_wallet_address", "")

        if not wallet_address:
            kb = [[InlineKeyboardButton("\U0001f50d Wallet Tracker", callback_data="wallet_tracker_menu")]]
            await update.message.reply_text("\u26a0\ufe0f Something went wrong. Please try again.",
                reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return

        result = add_tracked_wallet(user_id, wallet_address, label)
        if "error" in result:
            kb = [[InlineKeyboardButton("\U0001f50d Wallet Tracker", callback_data="wallet_tracker_menu")]]
            await update.message.reply_text(f"\u26a0\ufe0f {result['error']}",
                reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
        else:
            kb = [[InlineKeyboardButton("View Tracked Wallets \U0001f0cf", callback_data="wallet_tracker_menu")],
                  [InlineKeyboardButton("Main Menu", callback_data="home")]]
            await update.message.reply_text(
                f"\u2705 Wallet Added Successfully!\n\n"
                f"Label: {label}\n"
                f"\U0001f4cd Address: {wallet_address[:8]}...{wallet_address[-6:]}\n\n"
                f"\U0001f514 You will receive notifications when this wallet makes trades.\n"
                f"\u23f0 Checking every {WALLET_CHECK_INTERVAL // 60} minutes.",
                reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
            )
        return

    # ===== WAITING FOR FEEDBACK =====
    if context.user_data.get("waiting_for_feedback"):
        context.user_data["waiting_for_feedback"] = False
        add_feedback(user_id, username, text)
        kb = [[InlineKeyboardButton("Main Menu", callback_data="home")]]
        await update.message.reply_text(
            "✅ Thank you for your feedback!\n\n"
            "Your message has been sent to the kodark.io team.\n"
            "We appreciate your input!",
            reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
        )
        # Notify admin
        try:
            if ADMIN_USER_ID:
                await context.bot.send_message(
                    chat_id=ADMIN_USER_ID,
                    text=f"📩 New Feedback!\n\nFrom: @{username} (ID: {user_id})\n\n\"{text[:500]}\"",
                    disable_web_page_preview=True,
                )
        except Exception as e:
            logger.error(f"Admin feedback notification error: {e}")
        return

    # ===== WAITING FOR ALARM VALUE =====
    if context.user_data.get("waiting_for_alarm_value"):
        context.user_data["waiting_for_alarm_value"] = False
        alarm_type = context.user_data.get("setting_alarm_type")
        token_address = context.user_data.get("current_token_address")
        token_name = context.user_data.get("current_token_name", "Unknown")
        token_symbol = context.user_data.get("current_token_symbol", "???")
        current_price = context.user_data.get("current_token_price_float", 0)

        try:
            value = float(text.replace(",", "."))
            if value <= 0:
                raise ValueError("Must be positive")
        except ValueError:
            kb = [[InlineKeyboardButton("Try Again", callback_data="action_alarm")], [InlineKeyboardButton("Main Menu", callback_data="home")]]
            await update.message.reply_text("⚠️ Invalid value. Please enter a valid number.", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return

        # Check alarm access again before setting
        paywall = _check_alarm_access(user_id, lang)
        if paywall:
            kb = [
                [InlineKeyboardButton("Upgrade Premium - from $18.49", callback_data="buy_premium")],
                [InlineKeyboardButton("Main Menu", callback_data="home")],
            ]
            await update.message.reply_text(paywall, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return

        result = add_price_alarm(user_id, token_address, token_name, token_symbol, alarm_type, value, current_price)

        if "error" in result:
            kb = [[InlineKeyboardButton("Main Menu", callback_data="home")]]
            await update.message.reply_text(f"⚠️ {result['error']}", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
        else:
            # Increment alarm count for free tier tracking
            increment_alarm_count(user_id)
            alarm = result["alarm"]
            kb = [
                [InlineKeyboardButton("My Alarms \u2666\ufe0f", callback_data="my_alarms")],
                [InlineKeyboardButton("New Analysis \U0001f0cf", callback_data="start_analyzing")],
                [InlineKeyboardButton("Main Menu", callback_data="home")],
            ]
            await update.message.reply_text(
                f"✅ Price Alarm Set!\n\n"
                f"{format_alarm_text(alarm)}\n\n"
                f"You will be notified when the condition is met.\n"
                f"Monitoring runs every 2 minutes.",
                reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
            )
        return

    # ===== WAITING FOR TOKEN ADDRESS =====
    if context.user_data.get("waiting_for_token"):
        context.user_data["waiting_for_token"] = False

        # Check analysis access
        paywall = _check_analysis_access(user_id, lang)
        if paywall:
            kb = [
                [InlineKeyboardButton("Upgrade Premium - from $18.49", callback_data="buy_premium")],
                [InlineKeyboardButton("Main Menu", callback_data="home")],
            ]
            await update.message.reply_text(paywall, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return

        token_address = text

        if len(token_address) < 32 or len(token_address) > 50:
            await update.message.reply_text(
                "⚠️ Invalid token address. Please send a valid Solana memecoin address.\n"
                "Try again with START ANALYZING.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("START ANALYZING \U0001f0cf", callback_data="start_analyzing")]]),
                disable_web_page_preview=True,
            )
            return

        loading_msg = await update.message.reply_text("⏳ Fetching token data...", disable_web_page_preview=True)

        try:
            token_data = get_token_info(token_address)
            if "error" in token_data:
                await loading_msg.edit_text(f"❌ Error: {token_data['error']}", disable_web_page_preview=True)
                return

            token_name = token_data.get("name", "Unknown")
            token_symbol = token_data.get("symbol", "???")
            price_usd = token_data.get("price_usd", "0")
            mcap = float(token_data.get("market_cap", 0) or 0)
            change_24h = float(token_data.get("price_change_24h", 0) or 0)
            change_emoji = "🟢" if change_24h >= 0 else "🔴"

            context.user_data["current_token_address"] = token_address
            context.user_data["current_token_name"] = token_name
            context.user_data["current_token_symbol"] = token_symbol
            context.user_data["current_token_price"] = price_usd
            context.user_data["current_token_price_float"] = float(price_usd) if price_usd else 0
            context.user_data["current_token_data"] = token_data

            kb = [
                [InlineKeyboardButton("Start Analysis \u2666\ufe0f", callback_data="action_analysis")],
                [InlineKeyboardButton(get_text('btn_chart', lang), callback_data="action_chart")],
                [InlineKeyboardButton("Set Price Alarm \u2666\ufe0f", callback_data="action_alarm")],
                [InlineKeyboardButton("Whale Alert \u2663\ufe0f", callback_data="action_whale")],
                [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
            ]

            mcap_str = f"${mcap:,.0f}" if mcap > 0 else "N/A"

            await loading_msg.edit_text(
                f"{get_text('token_found', lang)}\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"📌 {token_name} (${token_symbol})\n"
                f"💰 Price: ${price_usd}\n"
                f"📊 Market Cap: {mcap_str}\n"
                f"📈 24h: {change_emoji} {change_24h:+.2f}%\n\n"
                f"{get_text('what_to_do', lang)}",
                reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
            )

        except Exception as e:
            logger.error(f"Token fetch error: {e}")
            await loading_msg.edit_text(f"❌ Error: {str(e)[:200]}", disable_web_page_preview=True)
        return

    # ===== AUTO-DETECT TOKEN ADDRESS =====
    if len(text) >= 32 and len(text) <= 50 and text.isalnum():
        paywall = _check_analysis_access(user_id, lang)
        if paywall:
            kb = [
                [InlineKeyboardButton("Upgrade Premium - from $18.49", callback_data="buy_premium")],
                [InlineKeyboardButton("Main Menu", callback_data="home")],
            ]
            await update.message.reply_text(paywall, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return

        context.user_data["waiting_for_token"] = True
        await handle_message(update, context)
    else:
        kb = [[InlineKeyboardButton("Main Menu", callback_data="home")]]
        await update.message.reply_text(
            "👋 Welcome to kodark.io!\n\n"
            "\U0001f0cf /start - Main Menu\n"
            "📖 /help - Help Guide\n"
            "💎 /premium - Premium Status\n"
            "💬 /feedback - Send Feedback\n\n"
            "Or just send a Solana memecoin address!",
            reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
        )


# ==================== BACKGROUND MONITORING ====================

async def background_price_check(app):
    """Background task: check price alarms every 2 minutes."""
    while True:
        try:
            await asyncio.sleep(120)

            watched_tokens = get_all_watched_tokens()
            if not watched_tokens:
                continue

            current_prices = {}
            for token_addr in watched_tokens:
                try:
                    token_data = get_token_info(token_addr)
                    if "error" not in token_data:
                        price = float(token_data.get("price_usd", 0) or 0)
                        change_24h = float(token_data.get("price_change_24h", 0) or 0)
                        current_prices[token_addr] = {"price": price, "change_24h": change_24h}
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"Price check error for {token_addr}: {e}")

            if not current_prices:
                continue

            triggered = check_alarms(current_prices)

            for t in triggered:
                try:
                    alarm = t["alarm"]
                    current_price = t["current_price"]
                    uid = t["user_id"]

                    # For free users, alarms still work if they were set within free tier
                    text = (
                        f"🔔 PRICE ALARM TRIGGERED!\n"
                        f"━━━━━━━━━━━━━━━\n\n"
                        f"{format_alarm_text(alarm)}\n\n"
                        f"💰 Current Price: ${current_price:,.8f}\n"
                        f"📅 Set on: {alarm.get('created_at', 'N/A')[:16]}\n\n"
                        f"⚡ This alarm has been deactivated."
                    )

                    await app.bot.send_message(chat_id=uid, text=text, disable_web_page_preview=True)
                except Exception as e:
                    logger.error(f"Alarm notification error: {e}")

        except Exception as e:
            logger.error(f"Background price check error: {e}")


async def background_whale_check(app):
    """Background task: check whale activity every 3 minutes."""
    while True:
        try:
            await asyncio.sleep(180)

            whale_tokens = get_all_whale_tokens()
            if not whale_tokens:
                continue

            for token_addr, user_ids in whale_tokens.items():
                try:
                    activity = check_whale_activity(token_addr)

                    if "error" in activity or not activity.get("has_activity"):
                        await asyncio.sleep(2)
                        continue

                    symbol = activity.get("symbol", "???")
                    alert_text = format_whale_alert_text(activity, symbol)

                    if alert_text:
                        for uid in user_ids:
                            try:
                                uid_premium = get_user_premium_status(uid)
                                if not uid_premium["is_premium"]:
                                    continue
                                await app.bot.send_message(chat_id=uid, text=alert_text, disable_web_page_preview=True)
                            except Exception as e:
                                logger.error(f"Whale alert send error for {uid}: {e}")

                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"Whale check error for {token_addr}: {e}")

        except Exception as e:
            logger.error(f"Background whale check error: {e}")


async def background_sniper_check(app):
    """Background task: check for new token launches every 5 minutes."""
    while True:
        try:
            await asyncio.sleep(300)

            platform_users = get_all_sniper_subscribers()
            has_subscribers = any(users for users in platform_users.values())
            if not has_subscribers:
                continue

            new_tokens = check_new_tokens()
            if not new_tokens:
                continue

            for token in new_tokens:
                platform = token.get("platform", "unknown")
                alert_text = format_sniper_alert(token)

                notified = set()
                for plat, users in platform_users.items():
                    if plat == platform or plat == "all":
                        for uid in users:
                            if uid in notified:
                                continue
                            try:
                                uid_premium = get_user_premium_status(uid)
                                if not uid_premium["is_premium"]:
                                    continue
                                await app.bot.send_message(chat_id=uid, text=alert_text, disable_web_page_preview=True)
                                notified.add(uid)
                            except Exception as e:
                                logger.error(f"Sniper alert send error for {uid}: {e}")

                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Background sniper check error: {e}")


async def background_wallet_tracker(app):
    """Background task: check tracked wallets for new transactions every 3 minutes."""
    while True:
        try:
            await asyncio.sleep(WALLET_CHECK_INTERVAL)

            all_trackers = get_all_wallet_trackers()
            if not all_trackers:
                continue

            for user_str, wallets in all_trackers.items():
                user_id = int(user_str)
                # Only check for premium users
                premium = get_user_premium_status(user_id)
                if not premium["is_premium"]:
                    continue

                for wallet in wallets:
                    try:
                        address = wallet["address"]
                        last_sig = wallet.get("last_tx_signature")

                        new_txs = await check_wallet_transactions(address, last_sig)
                        if not new_txs:
                            continue

                        # Update last known signature
                        update_wallet_last_tx(user_id, address, new_txs[0]["signature"])

                        # Get details and notify
                        for tx in new_txs[:2]:  # Max 2 notifications per check
                            if tx.get("err"):
                                continue
                            details = await get_transaction_details(tx["signature"])

                            # Build notification
                            tx_type_emoji = {
                                "buy_token": "\U0001f7e2 BUY",
                                "sell_token": "\U0001f534 SELL",
                                "send_sol": "\u27a1\ufe0f SEND",
                                "receive_sol": "\u2b05\ufe0f RECEIVE",
                                "unknown": "\U0001f504 TX",
                            }

                            type_text = tx_type_emoji.get(details.get("type", "unknown"), "\U0001f504 TX")
                            label = wallet.get("label", "Tracked Wallet")

                            alert_text = (
                                f"SMART MONEY ALERT \U0001f0cf\n"
                                f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
                                f"Wallet: {label}\n"
                                f"Address: {address[:6]}...{address[-4:]}\n\n"
                                f"Action: {type_text}\n"
                                f"Details: {details.get('details', 'N/A')}\n"
                                f"Fee: {details.get('fee', 0):.6f} SOL\n\n"
                                f"https://solscan.io/tx/{tx['signature']}\n\n"
                                f"\u2014 kodark.io"
                            )

                            try:
                                await app.bot.send_message(
                                    chat_id=user_id,
                                    text=alert_text,
                                    disable_web_page_preview=True
                                )
                            except Exception as e:
                                logger.error(f"Wallet alert send error for {user_id}: {e}")

                        await asyncio.sleep(1)
                    except Exception as e:
                        logger.error(f"Wallet tracker error for {wallet.get('address', '?')}: {e}")

                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Background wallet tracker error: {e}")


async def background_daily_summary(app):
    """Background task: send daily market summary to premium users at DAILY_SUMMARY_HOUR UTC."""
    last_sent_date = None
    while True:
        try:
            await asyncio.sleep(60)  # Check every minute

            if not DAILY_SUMMARY_ENABLED:
                continue

            now = datetime.now()
            current_hour = now.hour
            current_date = now.strftime("%Y-%m-%d")

            # Send at the configured hour, once per day
            if current_hour == DAILY_SUMMARY_HOUR and current_date != last_sent_date:
                last_sent_date = current_date
                logger.info("Sending daily market summary...")

                summary_text = await build_daily_summary_text()
                if not summary_text:
                    continue

                subscribers = get_daily_summary_subscribers()
                sent = 0
                for uid in subscribers:
                    try:
                        kb = InlineKeyboardMarkup([
                            [InlineKeyboardButton("\U0001f3b2 Analyze Token", callback_data="start_analyzing")],
                            [InlineKeyboardButton("\U0001f515 Disable Summary", callback_data="toggle_daily_summary")],
                        ])
                        await app.bot.send_message(
                            chat_id=uid,
                            text=summary_text,
                            reply_markup=kb,
                            disable_web_page_preview=True
                        )
                        sent += 1
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        logger.error(f"Daily summary send error for {uid}: {e}")

                logger.info(f"Daily summary sent to {sent}/{len(subscribers)} subscribers.")

        except Exception as e:
            logger.error(f"Background daily summary error: {e}")


async def post_init(app):
    """Start background tasks after bot initialization."""
    # Load campaign state from persistent data
    global CAMPAIGN_BUY1_GET1
    try:
        data = load_user_data()
        if "__campaign_buy1_get1" in data:
            CAMPAIGN_BUY1_GET1 = data["__campaign_buy1_get1"]
            logger.info(f"Campaign 1+1 loaded: {'ON' if CAMPAIGN_BUY1_GET1 else 'OFF'}")
    except Exception:
        pass

    asyncio.create_task(background_price_check(app))
    asyncio.create_task(background_whale_check(app))
    asyncio.create_task(background_sniper_check(app))
    asyncio.create_task(background_wallet_tracker(app))
    asyncio.create_task(background_daily_summary(app))
    asyncio.create_task(background_sol_payment_check(app))
    logger.info("Background monitoring tasks started (price, whale, sniper, wallet tracker, daily summary, sol payment).")


async def background_sol_payment_check(app):
    """Background task to auto-verify pending SOL payments."""
    while True:
        try:
            await asyncio.sleep(SOL_PAYMENT_CHECK_INTERVAL)
            data = load_user_data()
            now = datetime.now()

            for user_str, ud in list(data.items()):
                if user_str.startswith("__"):
                    continue
                pending = ud.get("pending_sol_payment")
                if not pending or pending.get("verified"):
                    continue

                # Check if expired (30 min)
                created = datetime.fromisoformat(pending["created"])
                if (now - created).total_seconds() > 1800:
                    data[user_str]["pending_sol_payment"] = None
                    save_user_data(data)
                    continue

                # Try to verify
                verified = await _verify_sol_payment(
                    SOL_WALLET_ADDRESS,
                    pending["amount_sol"],
                    pending["memo"],
                    pending["created"]
                )

                if verified:
                    plan_key = pending["plan"]
                    plan = PREMIUM_PLANS.get(plan_key, PREMIUM_PLANS["1_month"])
                    days = plan["days"]
                    if CAMPAIGN_BUY1_GET1 and plan_key == "1_month":
                        days = 60

                    user_id = int(user_str)
                    until = activate_premium(user_id, days=days)
                    data[user_str]["paid_premium"] = True
                    data[user_str]["pending_sol_payment"] = None
                    save_user_data(data)

                    bonus_text = ""
                    if CAMPAIGN_BUY1_GET1 and plan_key == "1_month":
                        bonus_text = "\n\U0001f0cf Campaign Bonus: +30 days FREE applied!"

                    try:
                        await app.bot.send_message(
                            chat_id=user_id,
                            text=(
                                f"Payment Verified \u2705\n\n"
                                f"Your {days}-day Premium subscription is now active!\n"
                                f"Expires: {until.strftime('%d.%m.%Y %H:%M')}\n"
                                f"{bonus_text}\n\n"
                                f"All premium features are unlocked.\n"
                                f"Thank you for your support!"
                            ),
                            disable_web_page_preview=True,
                        )
                    except Exception as e:
                        logger.error(f"Could not notify user {user_str} about payment: {e}")

                    logger.info(f"Auto-verified SOL payment for user {user_str}, plan: {plan_key}")

        except Exception as e:
            logger.error(f"Background SOL payment check error: {e}")


# ==================== MAIN ====================

def main():
    logger.info("kodark.io Bot v5.1 starting...")

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("premium", premium_command))
    app.add_handler(CommandHandler("feedback", feedback_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))

    # Payment handlers
    app.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))

    # Welcome handler for new chat members
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_user))

    # Callback & message handlers
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot v5.2 started successfully! Polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
