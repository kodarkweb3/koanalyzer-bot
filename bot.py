"""
KoAnalyzerBot - Solana Based Coins Analyzer Tool
Whale Watch | Holder Analysis | Risk Assessment
Telegram Stars Payment System
"""

import os
import json
import logging
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
    get_trending_solana_tokens,
)
from ai_analyzer import analyze_token

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

# Premium price in Telegram Stars
# ~$13.99 USD => approximately 1000 Stars (1 Star ~ $0.014)
PREMIUM_PRICE_STARS = 1000
PREMIUM_DAYS = 30

# Owner/Admin - always has unlimited premium (loaded from env)
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))

# Promo code settings (loaded from env)
PROMO_CODE = os.getenv("PROMO_CODE", "")
PROMO_DAYS = 3

# ==================== DATA STORAGE ====================

DATA_FILE = "user_data.json"

def load_user_data() -> dict:
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Data load error: {e}")
    return {}

def save_user_data(data: dict):
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Data save error: {e}")

def get_user_premium_status(user_id: int) -> dict:
    # Admin always has unlimited premium
    if user_id == ADMIN_USER_ID:
        return {
            "is_premium": True,
            "remaining": "Unlimited",
            "until": "Lifetime",
        }

    data = load_user_data()
    user_str = str(user_id)

    if user_str not in data:
        data[user_str] = {
            "premium": False,
            "premium_until": None,
            "analysis_count": 0,
            "promo_used": False,
            "joined": datetime.now().isoformat(),
        }
        save_user_data(data)

    user = data[user_str]

    if user.get("premium_until"):
        try:
            until = datetime.fromisoformat(user["premium_until"])
            if until > datetime.now():
                remaining = until - datetime.now()
                days = remaining.days
                hours = remaining.seconds // 3600
                return {
                    "is_premium": True,
                    "remaining": f"{days}d {hours}h",
                    "until": until.strftime("%d.%m.%Y %H:%M"),
                }
            else:
                user["premium"] = False
                user["premium_until"] = None
                data[user_str] = user
                save_user_data(data)
        except Exception:
            pass

    return {
        "is_premium": user.get("premium", False),
        "remaining": None,
        "until": None,
    }

def activate_premium(user_id: int, days: int = 30):
    data = load_user_data()
    user_str = str(user_id)

    if user_str not in data:
        data[user_str] = {
            "analysis_count": 0,
            "promo_used": False,
            "joined": datetime.now().isoformat(),
        }

    # If already premium, extend from current expiry
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

def has_used_promo(user_id: int) -> bool:
    data = load_user_data()
    user_str = str(user_id)
    if user_str in data:
        return data[user_str].get("promo_used", False)
    return False

def mark_promo_used(user_id: int):
    data = load_user_data()
    user_str = str(user_id)
    if user_str in data:
        data[user_str]["promo_used"] = True
        save_user_data(data)

def increment_analysis(user_id: int):
    data = load_user_data()
    user_str = str(user_id)
    if user_str in data:
        data[user_str]["analysis_count"] = data[user_str].get("analysis_count", 0) + 1
        data[user_str]["last_analysis"] = datetime.now().isoformat()
        save_user_data(data)

def record_user_activity(user_id: int, username: str = None, activity: str = "visit"):
    """Record user activity for admin tracking."""
    data = load_user_data()
    user_str = str(user_id)
    now = datetime.now().isoformat()

    if user_str not in data:
        data[user_str] = {
            "premium": False,
            "premium_until": None,
            "analysis_count": 0,
            "promo_used": False,
            "joined": now,
        }

    data[user_str]["last_active"] = now
    data[user_str]["username"] = username or data[user_str].get("username", "Unknown")

    # Track activity log (keep last 5 per user)
    if "activity_log" not in data[user_str]:
        data[user_str]["activity_log"] = []
    data[user_str]["activity_log"].append({"type": activity, "time": now})
    data[user_str]["activity_log"] = data[user_str]["activity_log"][-5:]

    # Global stats
    if "__stats__" not in data:
        data["__stats__"] = {
            "total_analyses": 0,
            "total_payments": 0,
            "total_promo_uses": 0,
            "daily_analyses": {},
            "daily_users": {},
        }

    today = datetime.now().strftime("%Y-%m-%d")

    if activity == "analysis":
        data["__stats__"]["total_analyses"] = data["__stats__"].get("total_analyses", 0) + 1
        data["__stats__"]["daily_analyses"][today] = data["__stats__"]["daily_analyses"].get(today, 0) + 1

    if activity == "payment":
        data["__stats__"]["total_payments"] = data["__stats__"].get("total_payments", 0) + 1

    if activity == "promo":
        data["__stats__"]["total_promo_uses"] = data["__stats__"].get("total_promo_uses", 0) + 1

    # Track daily unique users
    if today not in data["__stats__"]["daily_users"]:
        data["__stats__"]["daily_users"][today] = []
    if user_str not in data["__stats__"]["daily_users"][today]:
        data["__stats__"]["daily_users"][today].append(user_str)

    # Clean old daily data (keep last 30 days)
    for key in ["daily_analyses", "daily_users"]:
        dates = sorted(data["__stats__"][key].keys())
        while len(dates) > 30:
            del data["__stats__"][key][dates.pop(0)]

    save_user_data(data)


def get_admin_stats() -> dict:
    """Get comprehensive stats for admin panel."""
    data = load_user_data()
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    total_users = 0
    premium_users = 0
    active_today = 0
    active_24h = 0
    new_today = 0
    promo_users = 0
    total_analyses = 0
    recent_users = []

    for user_str, user_data_item in data.items():
        if user_str.startswith("__"):
            continue
        total_users += 1
        total_analyses += user_data_item.get("analysis_count", 0)

        # Premium check
        if user_data_item.get("premium_until"):
            try:
                until = datetime.fromisoformat(user_data_item["premium_until"])
                if until > now:
                    premium_users += 1
            except Exception:
                pass

        # Promo used
        if user_data_item.get("promo_used"):
            promo_users += 1

        # Active today
        last_active = user_data_item.get("last_active")
        if last_active:
            try:
                la = datetime.fromisoformat(last_active)
                if la.strftime("%Y-%m-%d") == today:
                    active_today += 1
                if (now - la).total_seconds() < 86400:
                    active_24h += 1
            except Exception:
                pass

        # New today
        joined = user_data_item.get("joined")
        if joined:
            try:
                jd = datetime.fromisoformat(joined)
                if jd.strftime("%Y-%m-%d") == today:
                    new_today += 1
            except Exception:
                pass

        # Recent users list
        username = user_data_item.get("username", "Unknown")
        recent_users.append({
            "id": user_str,
            "username": username,
            "analyses": user_data_item.get("analysis_count", 0),
            "premium": bool(user_data_item.get("premium")),
            "promo_used": bool(user_data_item.get("promo_used")),
            "last_active": last_active or joined or "",
            "joined": joined or "",
        })

    # Sort by last active
    recent_users.sort(key=lambda x: x.get("last_active", ""), reverse=True)

    # Global stats
    stats = data.get("__stats__", {})
    today_analyses = stats.get("daily_analyses", {}).get(today, 0)
    today_unique = len(stats.get("daily_users", {}).get(today, []))

    # 7-day analysis trend
    week_analyses = []
    for i in range(6, -1, -1):
        d = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        count = stats.get("daily_analyses", {}).get(d, 0)
        day_name = (now - timedelta(days=i)).strftime("%a")
        week_analyses.append(f"{day_name}: {count}")

    return {
        "total_users": total_users,
        "premium_users": premium_users,
        "active_today": active_today,
        "active_24h": active_24h,
        "new_today": new_today,
        "promo_users": promo_users,
        "total_analyses": total_analyses,
        "today_analyses": today_analyses,
        "today_unique": today_unique,
        "total_payments": stats.get("total_payments", 0),
        "week_trend": " | ".join(week_analyses),
        "recent_users": recent_users[:10],
    }


# ==================== HELPER: BUILD TEXTS ====================

def build_start_text(premium: dict) -> str:
    if premium["is_premium"]:
        if premium["remaining"] == "Unlimited":
            status_line = "✅ Premium Status: Active (Lifetime)"
        else:
            status_line = f"✅ Premium Status: Active ({premium['remaining']} left)"
    else:
        status_line = "❌ Premium Status: Inactive"

    # Payment trust line for non-premium users
    if premium["is_premium"]:
        payment_line = ""
    else:
        payment_line = "\n💳 Pay securely via Telegram Stars\n"

    text = (
        f"🚀 Solana Memecoins Analyzer Tool\n"
        f"\n"
        f"🔥 The ultimate intelligence tool for Solana memecoins & tokens.\n"
        f"Analyze any Solana memecoin before you ape in!\n"
        f"\n"
        f"⚡ Features:\n"
        f"\n"
        f"🐋 Whale Watch\n"
        f"Track large wallet movements and detect whale activity in real-time.\n"
        f"\n"
        f"🛡 Risk Assessment\n"
        f"Scan memecoins for rug pull risks, mint/freeze authority and security threats.\n"
        f"\n"
        f"📊 Holder Analysis\n"
        f"Analyze top holder distribution, insider percentage and token concentration.\n"
        f"\n"
        f"📈 Market Signals\n"
        f"Live Fear & Greed Index, BTC Dominance and SOL price tracking.\n"
        f"\n"
        f"🔍 Memecoin Analysis\n"
        f"Deep dive into any Solana memecoin with liquidity, volume and price data.\n"
        f"\n"
        f"{status_line}"
        f"{payment_line}"
        f"\n"
        f"🔗 x.com/kodarkweb3\n"
        f"\n"
        f"👇 Select an option to get started:"
    )
    return text


def build_start_keyboard(is_premium: bool) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🚀 Start General Analysis", callback_data="analyze")],
        [InlineKeyboardButton("📈 Market Signals", callback_data="signals")],
    ]
    if is_premium:
        keyboard.append([InlineKeyboardButton("💎 Premium Status", callback_data="premium")])
    else:
        keyboard.append([InlineKeyboardButton("💎 Buy Premium - ~$13.99", callback_data="premium")])
        keyboard.append([InlineKeyboardButton("🎁 Promo Code", callback_data="promo_info")])
    keyboard.append([InlineKeyboardButton("🗺 Roadmap", callback_data="roadmap")])
    return InlineKeyboardMarkup(keyboard)


def _build_premium_text(premium: dict) -> str:
    if premium["is_premium"]:
        remaining = premium['remaining']
        until = premium['until']
        return (
            f"💎 PREMIUM STATUS\n\n"
            f"✅ Status: Active\n"
            f"⏰ Remaining: {remaining}\n"
            f"📅 Expires: {until}\n\n"
            f"🔓 All premium features are unlocked!\n"
            f"Enjoy unlimited token analysis."
        )
    else:
        return (
            f"💎 PREMIUM STATUS\n\n"
            f"❌ Status: Inactive\n\n"
            f"🔒 Premium features include:\n"
            f"🔍 Unlimited token analysis\n"
            f"🤖 Advanced AI-powered reports\n"
            f"🐋 Whale alert notifications\n"
            f"⚡ Priority support\n\n"
            f"💰 Price: ~$13.99 ({PREMIUM_PRICE_STARS} Telegram Stars)\n"
            f"📅 Duration: {PREMIUM_DAYS} days\n\n"
            f"👇 Tap the button below to purchase:"
        )


def _check_premium_access(premium: dict) -> str:
    """Returns a paywall message if user is not premium, else empty string."""
    if premium["is_premium"]:
        return ""
    return (
        f"🔒 Premium Access Required\n\n"
        f"This feature is only available for Premium users.\n\n"
        f"💎 Get Premium for ~$13.99 ({PREMIUM_PRICE_STARS} Stars)\n"
        f"📅 {PREMIUM_DAYS} days of unlimited access\n\n"
        f"🔍 Unlimited token analysis\n"
        f"🤖 AI-powered reports\n"
        f"🐋 Whale tracking\n"
        f"🛡 Risk assessment\n\n"
        f"👇 Tap below to unlock:"
    )


# ==================== COMMANDS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or "Unknown"
    record_user_activity(user_id, username, "visit")
    premium = get_user_premium_status(user_id)
    welcome_text = build_start_text(premium)
    reply_markup = build_start_keyboard(premium["is_premium"])

    await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup,
    )


# ==================== ADMIN PANEL ====================

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panel - only accessible by ADMIN_USER_ID."""
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("⛔ Access denied.")
        return

    stats = get_admin_stats()
    text = _build_admin_panel_text(stats)
    keyboard = _build_admin_keyboard()
    await update.message.reply_text(text, reply_markup=keyboard)


def _build_admin_panel_text(stats: dict) -> str:
    """Build the main admin panel text."""
    now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    return (
        f"📊 ADMIN PANEL\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 USERS\n"
        f"├ Total Users: {stats['total_users']}\n"
        f"├ New Today: {stats['new_today']}\n"
        f"├ Active Today: {stats['active_today']}\n"
        f"└ Active (24h): {stats['active_24h']}\n\n"
        f"💎 PREMIUM\n"
        f"├ Active Premium: {stats['premium_users']}\n"
        f"├ Total Payments: {stats['total_payments']}\n"
        f"└ Promo Used: {stats['promo_users']}\n\n"
        f"🔍 ANALYSES\n"
        f"├ Total: {stats['total_analyses']}\n"
        f"├ Today: {stats['today_analyses']}\n"
        f"└ Today Unique Users: {stats['today_unique']}\n\n"
        f"📈 WEEKLY TREND (Analyses)\n"
        f"{stats['week_trend']}\n\n"
        f"🕐 Updated: {now}"
    )


def _build_admin_keyboard() -> InlineKeyboardMarkup:
    """Build admin panel inline keyboard."""
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh Stats", callback_data="admin_refresh")],
        [InlineKeyboardButton("👥 Recent Users", callback_data="admin_users")],
        [InlineKeyboardButton("💎 Premium Users", callback_data="admin_premium_list")],
        [InlineKeyboardButton("📊 Detailed Analytics", callback_data="admin_analytics")],
        [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast_info")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
    ]
    return InlineKeyboardMarkup(keyboard)


def _build_recent_users_text(stats: dict) -> str:
    """Build recent users list text."""
    text = "👥 RECENT USERS (Last Active)\n━━━━━━━━━━━━━━━━━━━━\n\n"
    if not stats["recent_users"]:
        text += "No users yet."
        return text

    for i, user in enumerate(stats["recent_users"], 1):
        premium_badge = "💎" if user["premium"] else "⬜"
        promo_badge = "🎁" if user["promo_used"] else ""
        username = user["username"] or "Unknown"
        # Format last active
        la = user.get("last_active", "")
        if la:
            try:
                la_dt = datetime.fromisoformat(la)
                la = la_dt.strftime("%d.%m %H:%M")
            except Exception:
                la = "N/A"
        text += (
            f"{i}. {premium_badge} @{username} {promo_badge}\n"
            f"   ID: {user['id']} | Analyses: {user['analyses']}\n"
            f"   Last: {la}\n\n"
        )
    return text


def _build_premium_users_text(stats: dict) -> str:
    """Build premium users list."""
    data = load_user_data()
    now = datetime.now()
    text = "💎 PREMIUM USERS\n━━━━━━━━━━━━━━━━━━━━\n\n"
    count = 0

    for user_str, user_data_item in data.items():
        if user_str.startswith("__"):
            continue
        if user_data_item.get("premium_until"):
            try:
                until = datetime.fromisoformat(user_data_item["premium_until"])
                if until > now:
                    count += 1
                    remaining = until - now
                    days = remaining.days
                    hours = remaining.seconds // 3600
                    username = user_data_item.get("username", "Unknown")
                    text += (
                        f"{count}. @{username}\n"
                        f"   ID: {user_str}\n"
                        f"   Remaining: {days}d {hours}h\n"
                        f"   Expires: {until.strftime('%d.%m.%Y %H:%M')}\n\n"
                    )
            except Exception:
                pass

    if count == 0:
        text += "No active premium users."
    else:
        text += f"\nTotal: {count} premium user(s)"
    return text


def _build_analytics_text() -> str:
    """Build detailed analytics text."""
    data = load_user_data()
    stats_data = data.get("__stats__", {})
    now = datetime.now()

    # Daily user counts for last 7 days
    text = "📊 DETAILED ANALYTICS\n━━━━━━━━━━━━━━━━━━━━\n\n"
    text += "📅 DAILY BREAKDOWN (Last 7 Days)\n\n"
    text += f"{'Date':<12} {'Users':<8} {'Analyses':<10}\n"
    text += f"{'─'*30}\n"

    for i in range(6, -1, -1):
        d = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        d_display = (now - timedelta(days=i)).strftime("%d.%m")
        day_name = (now - timedelta(days=i)).strftime("%a")
        users = len(stats_data.get("daily_users", {}).get(d, []))
        analyses = stats_data.get("daily_analyses", {}).get(d, 0)
        marker = " ◀" if i == 0 else ""
        text += f"{day_name} {d_display}   {users:<8} {analyses:<10}{marker}\n"

    # Conversion stats
    total_users = sum(1 for k in data if not k.startswith("__"))
    promo_users = sum(1 for k, v in data.items() if not k.startswith("__") and v.get("promo_used"))
    paid_users = stats_data.get("total_payments", 0)

    text += f"\n💰 CONVERSION\n"
    if total_users > 0:
        promo_rate = (promo_users / total_users) * 100
        paid_rate = (paid_users / total_users) * 100
        text += f"├ Promo Rate: {promo_rate:.1f}% ({promo_users}/{total_users})\n"
        text += f"└ Paid Rate: {paid_rate:.1f}% ({paid_users}/{total_users})\n"
    else:
        text += "├ No data yet\n"

    # Revenue estimate
    revenue = paid_users * 13.99
    text += f"\n💵 ESTIMATED REVENUE\n"
    text += f"└ ~${revenue:.2f} ({paid_users} payment(s))\n"

    text += f"\n🕐 Generated: {now.strftime('%d.%m.%Y %H:%M:%S')}"
    return text


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    help_text = (
        "📖 KoAnalyzer Bot - Help Guide\n\n"
        "🚀 Available Commands:\n\n"
        "/start - Open main menu\n"
        "/analyze - Start token analysis\n"
        "/signals - View market signals\n"
        "/premium - Check premium status\n"
        "/help - Show this help guide\n\n"
        "🔍 How to Analyze a Token:\n"
        "1. Tap 'Start General Analysis' or use /analyze\n"
        "2. Send the Solana token contract address\n"
        "3. Wait for the comprehensive report\n\n"
        "📊 Report Includes:\n"
        "  General Overview & Market Position\n"
        "  Liquidity & Volume Analysis\n"
        "  Multi-Timeframe Price Action\n"
        "  Security & Rug Pull Assessment\n"
        "  Whale & Holder Distribution\n"
        "  Transaction Flow Analysis\n"
        "  Final Verdict & Score\n\n"
        "💎 Premium gives you unlimited access to all features.\n\n"
        "🔗 x.com/kodarkweb3"
    )

    keyboard = [
        [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
    ]

    await update.message.reply_text(
        help_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    premium = get_user_premium_status(user_id)

    paywall = _check_premium_access(premium)
    if paywall:
        keyboard = [
            [InlineKeyboardButton("💎 Buy Premium - ~$13.99", callback_data="buy_premium")],
            [InlineKeyboardButton("🎁 Promo Code", callback_data="promo_info")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
        ]
        await update.message.reply_text(paywall, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    await update.message.reply_text(
        "🔍 Token Analysis\n\n"
        "Send the Solana token address you want to analyze:\n\n"
        "Example: So11111111111111111111111111111111111111112",
    )
    context.user_data["waiting_for_token"] = True


async def signals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    premium = get_user_premium_status(user_id)

    paywall = _check_premium_access(premium)
    if paywall:
        keyboard = [
            [InlineKeyboardButton("💎 Buy Premium - ~$13.99", callback_data="buy_premium")],
            [InlineKeyboardButton("🎁 Promo Code", callback_data="promo_info")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
        ]
        await update.message.reply_text(paywall, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    msg = await update.message.reply_text("⏳ Loading market data...")
    await _send_signals(msg, user_id)


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

        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="signals")],
            [InlineKeyboardButton("🚀 Start General Analysis", callback_data="analyze")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await msg.edit_text(signals_text, reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Signals error: {e}")
        await msg.edit_text(f"❌ Error fetching market data: {str(e)[:200]}")


async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    premium = get_user_premium_status(user_id)
    text = _build_premium_text(premium)

    if premium["is_premium"]:
        keyboard = [
            [InlineKeyboardButton("🚀 Start General Analysis", callback_data="analyze")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("💎 Buy Premium - ~$13.99", callback_data="buy_premium")],
            [InlineKeyboardButton("🎁 Promo Code", callback_data="promo_info")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
        ]

    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


# ==================== PROMO CODE SYSTEM ====================

async def promo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hidden promo command - free trial (one-time use per user, available to anyone who knows the code)."""
    user_id = update.effective_user.id
    premium = get_user_premium_status(user_id)

    # Already premium
    if premium["is_premium"]:
        await update.message.reply_text(
            f"✅ You already have an active premium subscription!\n"
            f"Remaining: {premium['remaining']}",
        )
        return

    # Check if already used promo (one-time per user)
    if has_used_promo(user_id):
        keyboard = [
            [InlineKeyboardButton("💎 Buy Premium - ~$13.99", callback_data="buy_premium")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
        ]
        await update.message.reply_text(
            "⚠️ You have already used your free trial.\n\n"
            "Each user can only use the promo code once.\n"
            "To continue using KoAnalyzer, please purchase Premium.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # Activate free trial and mark as used
    until = activate_premium(user_id, days=PROMO_DAYS)
    mark_promo_used(user_id)
    username = update.effective_user.username or update.effective_user.first_name or "Unknown"
    record_user_activity(user_id, username, "promo")
    date_str = until.strftime('%d.%m.%Y %H:%M')

    keyboard = [
        [InlineKeyboardButton("🚀 Start General Analysis", callback_data="analyze")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
    ]

    await update.message.reply_text(
        f"🎉 Promo Code Activated!\n\n"
        f"Your {PROMO_DAYS}-day free trial has been activated!\n"
        f"📅 Expires: {date_str}\n\n"
        f"🔓 All premium features are now unlocked.\n"
        f"Enjoy your free trial!",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ==================== TELEGRAM STARS PAYMENT ====================

async def send_premium_invoice(update_or_query, context: ContextTypes.DEFAULT_TYPE):
    """Send a Telegram Stars invoice for premium subscription."""
    # Determine chat_id
    if hasattr(update_or_query, 'message') and update_or_query.message:
        chat_id = update_or_query.message.chat_id
    elif hasattr(update_or_query, 'from_user'):
        chat_id = update_or_query.from_user.id
    else:
        chat_id = update_or_query.effective_chat.id

    await context.bot.send_invoice(
        chat_id=chat_id,
        title="KoAnalyzer Premium Subscription",
        description=f"Unlock {PREMIUM_DAYS}-day Premium Access\n\n"
                    f"Unlimited token analysis\n"
                    f"AI-powered reports\n"
                    f"Whale tracking & alerts\n"
                    f"Risk assessment tools\n"
                    f"Priority support",
        payload="premium_subscription",
        provider_token="",  # Empty for Telegram Stars
        currency="XTR",     # Telegram Stars currency
        prices=[LabeledPrice(label="Premium Subscription", amount=PREMIUM_PRICE_STARS)],
    )


async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pre-checkout query - must respond within 10 seconds."""
    query = update.pre_checkout_query
    logger.info(f"Pre-checkout from user {query.from_user.id}, payload: {query.invoice_payload}")

    if query.invoice_payload == "premium_subscription":
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Unknown payment type.")


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle successful payment - activate premium."""
    payment = update.message.successful_payment
    user_id = update.effective_user.id

    logger.info(
        f"Successful payment from user {user_id}: "
        f"{payment.total_amount} {payment.currency}, "
        f"payload: {payment.invoice_payload}"
    )

    if payment.invoice_payload == "premium_subscription":
        until = activate_premium(user_id, days=PREMIUM_DAYS)
        username = update.effective_user.username or update.effective_user.first_name or "Unknown"
        record_user_activity(user_id, username, "payment")
        date_str = until.strftime('%d.%m.%Y %H:%M')

        keyboard = [
            [InlineKeyboardButton("🚀 Start General Analysis", callback_data="analyze")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
        ]

        await update.message.reply_text(
            f"🎉 Payment Successful!\n\n"
            f"✅ Your {PREMIUM_DAYS}-day Premium subscription is now active!\n"
            f"📅 Expires: {date_str}\n\n"
            f"🔓 All premium features are unlocked.\n"
            f"Enjoy unlimited token analysis!",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


# ==================== CALLBACK HANDLER ====================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "home":
        user_id = query.from_user.id
        premium = get_user_premium_status(user_id)
        welcome_text = build_start_text(premium)
        reply_markup = build_start_keyboard(premium["is_premium"])
        await query.edit_message_text(welcome_text, reply_markup=reply_markup)

    elif query.data == "analyze":
        user_id = query.from_user.id
        premium = get_user_premium_status(user_id)

        paywall = _check_premium_access(premium)
        if paywall:
            keyboard = [
                [InlineKeyboardButton("💎 Buy Premium - ~$13.99", callback_data="buy_premium")],
                [InlineKeyboardButton("🎁 Promo Code", callback_data="promo_info")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
            ]
            await query.edit_message_text(paywall, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        await query.edit_message_text(
            "🔍 Token Analysis\n\n"
            "Send the Solana token address you want to analyze:\n\n"
            "Example: So11111111111111111111111111111111111111112",
        )
        context.user_data["waiting_for_token"] = True

    elif query.data == "signals":
        user_id = query.from_user.id
        premium = get_user_premium_status(user_id)

        paywall = _check_premium_access(premium)
        if paywall:
            keyboard = [
                [InlineKeyboardButton("💎 Buy Premium - ~$13.99", callback_data="buy_premium")],
                [InlineKeyboardButton("🎁 Promo Code", callback_data="promo_info")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
            ]
            await query.edit_message_text(paywall, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        await query.edit_message_text("⏳ Loading market data...")
        await _send_signals(query.message, user_id)

    elif query.data == "premium":
        user_id = query.from_user.id
        premium = get_user_premium_status(user_id)
        text = _build_premium_text(premium)

        if premium["is_premium"]:
            keyboard = [
                [InlineKeyboardButton("🚀 Start General Analysis", callback_data="analyze")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("💎 Buy Premium - ~$13.99", callback_data="buy_premium")],
                [InlineKeyboardButton("🎁 Promo Code", callback_data="promo_info")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
            ]

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "buy_premium":
        # Send Telegram Stars invoice
        await send_premium_invoice(query, context)

    elif query.data == "promo_info":
        user_id = query.from_user.id
        premium = get_user_premium_status(user_id)

        if premium["is_premium"]:
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
            ]
            await query.edit_message_text(
                "✅ You already have an active premium subscription!",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return

        keyboard = [
            [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
        ]
        await query.edit_message_text(
            "🎁 Promo Code\n\n"
            f"Get a {PROMO_DAYS}-day free trial!\n\n"
            "If you have a promo code, send it as a command.\n"
            "Example: /yourcode",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    # ==================== ADMIN CALLBACKS ====================
    elif query.data == "admin_refresh":
        user_id = query.from_user.id
        if user_id != ADMIN_USER_ID:
            await query.edit_message_text("\u26d4 Access denied.")
            return
        stats = get_admin_stats()
        text = _build_admin_panel_text(stats)
        keyboard = _build_admin_keyboard()
        await query.edit_message_text(text, reply_markup=keyboard)

    elif query.data == "admin_users":
        user_id = query.from_user.id
        if user_id != ADMIN_USER_ID:
            await query.edit_message_text("\u26d4 Access denied.")
            return
        stats = get_admin_stats()
        text = _build_recent_users_text(stats)
        keyboard = [
            [InlineKeyboardButton("\ud83d\udd04 Refresh", callback_data="admin_users")],
            [InlineKeyboardButton("\u25c0\ufe0f Back to Panel", callback_data="admin_refresh")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "admin_premium_list":
        user_id = query.from_user.id
        if user_id != ADMIN_USER_ID:
            await query.edit_message_text("\u26d4 Access denied.")
            return
        stats = get_admin_stats()
        text = _build_premium_users_text(stats)
        keyboard = [
            [InlineKeyboardButton("\ud83d\udd04 Refresh", callback_data="admin_premium_list")],
            [InlineKeyboardButton("\u25c0\ufe0f Back to Panel", callback_data="admin_refresh")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "admin_analytics":
        user_id = query.from_user.id
        if user_id != ADMIN_USER_ID:
            await query.edit_message_text("\u26d4 Access denied.")
            return
        text = _build_analytics_text()
        keyboard = [
            [InlineKeyboardButton("\ud83d\udd04 Refresh", callback_data="admin_analytics")],
            [InlineKeyboardButton("\u25c0\ufe0f Back to Panel", callback_data="admin_refresh")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "admin_broadcast_info":
        user_id = query.from_user.id
        if user_id != ADMIN_USER_ID:
            await query.edit_message_text("\u26d4 Access denied.")
            return
        keyboard = [
            [InlineKeyboardButton("\u25c0\ufe0f Back to Panel", callback_data="admin_refresh")],
        ]
        await query.edit_message_text(
            "\ud83d\udce2 BROADCAST MESSAGE\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            "Send a broadcast to all users:\n\n"
            "Use the command:\n"
            "/broadcast Your message here\n\n"
            "This will send your message to all registered users.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif query.data == "roadmap":
        keyboard = [
            [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
        ]
        await query.edit_message_text(
            "🗺 ROADMAP - Upcoming Features\n\n"
            "We are constantly working to make KoAnalyzer\n"
            "the best Solana intelligence tool.\n\n"
            "🔜 Coming Soon:\n\n"
            "🔔 Whale Alert Notifications\n"
            "Real-time push alerts when whales buy or sell tokens you track.\n\n"
            "🌐 Multi-Language Support\n"
            "Full support for Turkish, Spanish, Chinese and more.\n\n"
            "👥 Referral System\n"
            "Invite friends and earn free premium days.\n\n"
            "📊 Portfolio Tracker\n"
            "Track your Solana wallet holdings and PnL in real-time.\n\n"
            "🤖 Auto-Sniper Alerts\n"
            "Get notified about new token launches matching your criteria.\n\n"
            "📉 Advanced Charting\n"
            "Interactive price charts and technical indicators inside Telegram.\n\n"
            "🛡 Watchlist\n"
            "Save your favorite tokens and get daily reports.\n\n"
            "Stay tuned for updates!\n\n"
            "🔗 x.com/kodarkweb3",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


# ==================== BROADCAST COMMAND ====================

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast a message to all users. Admin only."""
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("\u26d4 Access denied.")
        return

    # Get the message text after /broadcast
    if not context.args:
        await update.message.reply_text(
            "Usage: /broadcast Your message here\n\n"
            "Example: /broadcast \ud83d\ude80 New update! Check out our latest features."
        )
        return

    broadcast_text = " ".join(context.args)
    data = load_user_data()
    sent = 0
    failed = 0

    status_msg = await update.message.reply_text("\ud83d\udce2 Broadcasting...")

    for user_str in data:
        if user_str.startswith("__"):
            continue
        try:
            await context.bot.send_message(
                chat_id=int(user_str),
                text=f"\ud83d\udce2 Announcement\n\n{broadcast_text}\n\n\u2014 KoAnalyzer Team",
            )
            sent += 1
        except Exception as e:
            logger.warning(f"Broadcast failed for {user_str}: {e}")
            failed += 1

    await status_msg.edit_text(
        f"\u2705 Broadcast Complete!\n\n"
        f"\u2714\ufe0f Sent: {sent}\n"
        f"\u274c Failed: {failed}\n"
        f"\ud83d\udcac Total: {sent + failed}"
    )


# ==================== MESSAGE HANDLER ====================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Record activity for all users
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or "Unknown"
    record_user_activity(user_id, username, "message")

    if context.user_data.get("waiting_for_token"):
        context.user_data["waiting_for_token"] = False
        token_address = update.message.text.strip()

        # Check premium again
        user_id = update.effective_user.id
        premium = get_user_premium_status(user_id)
        paywall = _check_premium_access(premium)
        if paywall:
            keyboard = [
                [InlineKeyboardButton("💎 Buy Premium - ~$13.99", callback_data="buy_premium")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
            ]
            await update.message.reply_text(paywall, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if len(token_address) < 32 or len(token_address) > 50:
            await update.message.reply_text(
                "⚠️ Invalid token address. Please send a valid Solana token address.\n"
                "Try again with /analyze",
            )
            return

        loading_msg = await update.message.reply_text(
            "⏳ Analysis in progress...\n\n"
            "🔄 Fetching DexScreener data...\n"
            "🔄 Running RugCheck security scan...\n"
            "🔄 Analyzing whale & holder data...\n"
            "🔄 Generating comprehensive report...",
        )

        try:
            token_data = get_token_info(token_address)

            if "error" in token_data:
                await loading_msg.edit_text(f"❌ Error: {token_data['error']}")
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
            record_user_activity(user_id, username, "analysis")

            dex_url = token_data.get("url", f"https://dexscreener.com/solana/{token_address}")

            keyboard = [
                [InlineKeyboardButton("📈 DexScreener", url=dex_url)],
                [InlineKeyboardButton("🚀 New Analysis", callback_data="analyze")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if len(report) > 4000:
                parts = [report[i:i+4000] for i in range(0, len(report), 4000)]
                await loading_msg.edit_text(parts[0])
                for part in parts[1:]:
                    await update.message.reply_text(part)
                await update.message.reply_text("Analysis complete.", reply_markup=reply_markup)
            else:
                await loading_msg.edit_text(report, reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Analysis error: {e}")
            await loading_msg.edit_text(f"❌ Error during analysis: {str(e)[:200]}")

    else:
        text = update.message.text.strip()
        if len(text) >= 32 and len(text) <= 50 and text.isalnum():
            # Looks like a token address, check premium first
            user_id = update.effective_user.id
            premium = get_user_premium_status(user_id)
            paywall = _check_premium_access(premium)
            if paywall:
                keyboard = [
                    [InlineKeyboardButton("💎 Buy Premium - ~$13.99", callback_data="buy_premium")],
                    [InlineKeyboardButton("🎁 Promo Code", callback_data="promo_info")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
                ]
                await update.message.reply_text(paywall, reply_markup=InlineKeyboardMarkup(keyboard))
                return

            context.user_data["waiting_for_token"] = True
            await handle_message(update, context)
        else:
            keyboard = [
                [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
            ]
            await update.message.reply_text(
                "👋 Need help? Here are the available commands:\n\n"
                "🚀 /analyze - Token Analysis\n"
                "📈 /signals - Market Signals\n"
                "💎 /premium - Premium Status\n"
                "📖 /help - Help Guide\n"
                "🏠 /start - Main Menu\n\n"
                "Or just send a Solana token address directly!",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )


# ==================== MAIN ====================

def main():
    logger.info("KoAnalyzerBot starting...")

    app = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("analyze", analyze_command))
    app.add_handler(CommandHandler("signals", signals_command))
    app.add_handler(CommandHandler("premium", premium_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    if PROMO_CODE:
        app.add_handler(CommandHandler(PROMO_CODE, promo_command))

    # Payment handlers - MUST be before general message handler
    app.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))

    # Callback & message handlers
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started successfully! Polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
