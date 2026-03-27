"""
kodark.io - Solana Memecoins Analyzer Bot
Whale Watch | Holder Analysis | Risk Assessment | Price Alarms
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

PREMIUM_PRICE_STARS = 1000
PREMIUM_DAYS = 30
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))
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
    if user_id == ADMIN_USER_ID:
        return {"is_premium": True, "remaining": "Unlimited", "until": "Lifetime"}

    data = load_user_data()
    user_str = str(user_id)

    if user_str not in data:
        data[user_str] = {
            "premium": False, "premium_until": None,
            "analysis_count": 0, "promo_used": False,
            "joined": datetime.now().isoformat(),
        }
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
        data[user_str] = {
            "analysis_count": 0, "promo_used": False,
            "joined": datetime.now().isoformat(),
        }

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
    data = load_user_data()
    user_str = str(user_id)
    now = datetime.now().isoformat()

    if user_str not in data:
        data[user_str] = {
            "premium": False, "premium_until": None,
            "analysis_count": 0, "promo_used": False,
            "joined": now,
        }

    data[user_str]["last_active"] = now
    data[user_str]["username"] = username or data[user_str].get("username", "Unknown")

    if "activity_log" not in data[user_str]:
        data[user_str]["activity_log"] = []
    data[user_str]["activity_log"].append({"type": activity, "time": now})
    data[user_str]["activity_log"] = data[user_str]["activity_log"][-5:]

    if "__stats__" not in data:
        data["__stats__"] = {
            "total_analyses": 0, "total_payments": 0,
            "total_promo_uses": 0, "daily_analyses": {}, "daily_users": {},
        }

    today = datetime.now().strftime("%Y-%m-%d")

    if activity == "analysis":
        data["__stats__"]["total_analyses"] = data["__stats__"].get("total_analyses", 0) + 1
        data["__stats__"]["daily_analyses"][today] = data["__stats__"]["daily_analyses"].get(today, 0) + 1
    if activity == "payment":
        data["__stats__"]["total_payments"] = data["__stats__"].get("total_payments", 0) + 1
    if activity == "promo":
        data["__stats__"]["total_promo_uses"] = data["__stats__"].get("total_promo_uses", 0) + 1

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
    promo_users = 0
    total_analyses = 0
    recent_users = []

    for user_str, ud in data.items():
        if user_str.startswith("__"):
            continue
        total_users += 1
        total_analyses += ud.get("analysis_count", 0)

        if ud.get("premium_until"):
            try:
                until = datetime.fromisoformat(ud["premium_until"])
                if until > now:
                    premium_users += 1
            except Exception:
                pass

        if ud.get("promo_used"):
            promo_users += 1

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
            "premium": bool(ud.get("premium")),
            "promo_used": bool(ud.get("promo_used")),
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

    return {
        "total_users": total_users, "premium_users": premium_users,
        "active_today": active_today, "active_24h": active_24h,
        "new_today": new_today, "promo_users": promo_users,
        "total_analyses": total_analyses, "today_analyses": today_analyses,
        "today_unique": today_unique,
        "total_payments": stats.get("total_payments", 0),
        "week_trend": " | ".join(week_analyses),
        "recent_users": recent_users[:10],
    }


# ==================== PAYWALL CHECK ====================

def _check_premium_access(premium: dict) -> str:
    if premium["is_premium"]:
        return ""
    promo_hint = f"\n\n🎁 Or use /{PROMO_CODE} for a {PROMO_DAYS}-day free trial!" if PROMO_CODE else ""
    return (
        f"🔒 Premium Access Required\n\n"
        f"This feature is only available for Premium users.\n\n"
        f"💎 Get Premium for ~$13.99 ({PREMIUM_PRICE_STARS} Stars)\n"
        f"📅 {PREMIUM_DAYS} days of unlimited access\n\n"
        f"🔍 Unlimited token analysis\n"
        f"🤖 AI-powered reports\n"
        f"🐋 Whale tracking\n"
        f"⏰ Price alarms\n"
        f"🛡 Risk assessment\n\n"
        f"💳 Pay securely via Telegram Stars"
        f"{promo_hint}\n\n"
        f"👇 Tap below to unlock:"
    )


# ==================== START MENU ====================

def build_start_text(premium: dict) -> str:
    if premium["is_premium"]:
        if premium["remaining"] == "Unlimited":
            status_line = "✅ Premium Status: Active (Lifetime)"
        else:
            status_line = f"✅ Premium Status: Active ({premium['remaining']} left)\n📅 Expires: {premium['until']}"
    else:
        status_line = "❌ Premium Status: Inactive"

    payment_line = "" if premium["is_premium"] else "\n💳 Pay securely via Telegram Stars\n"

    promo_line = f"\n🎁 Use /{PROMO_CODE} for a {PROMO_DAYS}-day free trial!\n" if PROMO_CODE else ""

    text = (
        f"🚀 Solana Memecoins Analyzer\n"
        f"\n"
        f"🔥 The ultimate intelligence tool for Solana memecoins.\n"
        f"Analyze any token before you ape in!\n"
        f"\n"
        f"⚡ Features:\n"
        f"🐋 Whale Watch — Track large wallet movements\n"
        f"🛡 Risk Assessment — Rug pull detection & security scan\n"
        f"📊 Holder Analysis — Top holder distribution & insiders\n"
        f"⏰ Price Alarms — Get notified on price targets\n"
        f"📈 Market Signals — Fear & Greed, BTC Dom, SOL price\n"
        f"{promo_line}"
        f"\n"
        f"{status_line}"
        f"{payment_line}"
        f"\n"
        f"🔗 x.com/kodarkweb3\n"
        f"🔗 x.com/kodarkio\n"
        f"\n"
        f"👇 Select an option to get started:"
    )
    return text


def build_start_keyboard(is_premium: bool) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🃏 START ANALYZING", callback_data="start_analyzing")],
        [InlineKeyboardButton("📈 Market Signals", callback_data="signals")],
        [
            InlineKeyboardButton("⏰ My Alarms", callback_data="my_alarms"),
            InlineKeyboardButton("🐋 My Whale Alerts", callback_data="my_whale_alerts"),
        ],
        [InlineKeyboardButton("💎 Premium Status", callback_data="premium")],
    ]
    if not is_premium:
        keyboard.append([InlineKeyboardButton("🎁 Enter Promo Code", callback_data="promo_info")])
    keyboard.append([InlineKeyboardButton("🗺 Roadmap", callback_data="roadmap")])
    return InlineKeyboardMarkup(keyboard)


# ==================== COMMANDS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or "Unknown"
    record_user_activity(user_id, username, "visit")
    premium = get_user_premium_status(user_id)
    text = build_start_text(premium)
    kb = build_start_keyboard(premium["is_premium"])
    await update.message.reply_text(text, reply_markup=kb, disable_web_page_preview=True)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 kodark.io Bot - Help Guide\n\n"
        "🚀 Commands:\n\n"
        "/start - Main menu\n"
        "/help - This help guide\n"
        "/premium - Premium status\n"
        "/admin - Admin panel (admin only)\n\n"
        "🔍 How to Use:\n"
        "1. Tap 'START ANALYZING'\n"
        "2. Enter a Solana memecoin address\n"
        "3. Choose: Analysis, Price Alarm, or Whale Alert\n\n"
        "💎 Premium gives you unlimited access to all features.\n\n"
        "🔗 x.com/kodarkweb3\n"
        "🔗 x.com/kodarkio"
    )
    kb = [[InlineKeyboardButton("🏠 Main Menu", callback_data="home")]]
    await update.message.reply_text(help_text, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)


async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    premium = get_user_premium_status(user_id)
    text = _build_premium_text(premium)
    kb = _build_premium_keyboard(premium)
    await update.message.reply_text(text, reply_markup=kb, disable_web_page_preview=True)


def _build_premium_text(premium: dict) -> str:
    if premium["is_premium"]:
        if premium["remaining"] == "Unlimited":
            return (
                f"💎 PREMIUM STATUS\n\n"
                f"✅ Status: Active (Lifetime)\n\n"
                f"🔓 All premium features are unlocked!\n\n"
                f"Thank you for your support!"
            )
        else:
            return (
                f"💎 PREMIUM STATUS\n\n"
                f"✅ Status: Active\n"
                f"⏰ Remaining: {premium['remaining']}\n"
                f"📅 Expires: {premium['until']}\n\n"
                f"🔓 All premium features are unlocked!\n\n"
                f"🔄 Your subscription will need to be renewed\n"
                f"before the expiry date to keep access."
            )
    else:
        promo_text = f"\n🎁 Use /{PROMO_CODE} for a {PROMO_DAYS}-day free trial!\n" if PROMO_CODE else ""
        return (
            f"💎 PREMIUM STATUS\n\n"
            f"❌ Status: Inactive\n\n"
            f"🔒 Premium features include:\n"
            f"🔍 Unlimited token analysis\n"
            f"🤖 AI-powered reports\n"
            f"🐋 Whale alert notifications\n"
            f"⏰ Price alarm system\n"
            f"⚡ Priority support\n\n"
            f"💰 Price: ~$13.99 ({PREMIUM_PRICE_STARS} Telegram Stars)\n"
            f"📅 Duration: {PREMIUM_DAYS} days\n"
            f"{promo_text}\n"
            f"💳 Pay securely via Telegram Stars\n\n"
            f"👇 Tap the button below to purchase:"
        )


def _build_premium_keyboard(premium: dict) -> InlineKeyboardMarkup:
    if premium["is_premium"]:
        kb = [
            [InlineKeyboardButton("🃏 START ANALYZING", callback_data="start_analyzing")],
        ]
        if premium["remaining"] != "Unlimited":
            kb.append([InlineKeyboardButton("🔄 Renew Premium", callback_data="buy_premium")])
        kb.append([InlineKeyboardButton("🏠 Main Menu", callback_data="home")])
        return InlineKeyboardMarkup(kb)
    else:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 Buy Premium - ~$13.99", callback_data="buy_premium")],
            [InlineKeyboardButton("🎁 Enter Promo Code", callback_data="promo_info")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
        ])


# ==================== PROMO CODE ====================

async def promo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    premium = get_user_premium_status(user_id)

    if premium["is_premium"]:
        await update.message.reply_text(
            f"✅ You already have an active premium subscription!\nRemaining: {premium['remaining']}",
            disable_web_page_preview=True,
        )
        return

    if has_used_promo(user_id):
        kb = [
            [InlineKeyboardButton("💎 Buy Premium - ~$13.99", callback_data="buy_premium")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
        ]
        await update.message.reply_text(
            "⚠️ You have already used your free trial.\n\n"
            "Each user can only use the promo code once.\n"
            "To continue using kodark.io, please purchase Premium.",
            reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
        )
        return

    until = activate_premium(user_id, days=PROMO_DAYS)
    mark_promo_used(user_id)
    username = update.effective_user.username or update.effective_user.first_name or "Unknown"
    record_user_activity(user_id, username, "promo")
    date_str = until.strftime('%d.%m.%Y %H:%M')

    kb = [
        [InlineKeyboardButton("🃏 START ANALYZING", callback_data="start_analyzing")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
    ]
    await update.message.reply_text(
        f"🎉 Promo Code Activated!\n\n"
        f"Your {PROMO_DAYS}-day free trial has been activated!\n"
        f"📅 Expires: {date_str}\n\n"
        f"🔓 All premium features are now unlocked.\n"
        f"Enjoy your free trial!",
        reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
    )


# ==================== TELEGRAM STARS PAYMENT ====================

async def send_premium_invoice(update_or_query, context: ContextTypes.DEFAULT_TYPE):
    if hasattr(update_or_query, 'message') and update_or_query.message:
        chat_id = update_or_query.message.chat_id
    elif hasattr(update_or_query, 'from_user'):
        chat_id = update_or_query.from_user.id
    else:
        chat_id = update_or_query.effective_chat.id

    await context.bot.send_invoice(
        chat_id=chat_id,
        title="kodark.io Premium Subscription",
        description=f"Unlock {PREMIUM_DAYS}-day Premium Access\n\n"
                    f"Unlimited token analysis\n"
                    f"AI-powered reports\n"
                    f"Whale tracking & alerts\n"
                    f"Price alarm system\n"
                    f"Risk assessment tools",
        payload="premium_subscription",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Premium Subscription", amount=PREMIUM_PRICE_STARS)],
    )


async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    if query.invoice_payload == "premium_subscription":
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Unknown payment type.")


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    user_id = update.effective_user.id

    if payment.invoice_payload == "premium_subscription":
        until = activate_premium(user_id, days=PREMIUM_DAYS)
        username = update.effective_user.username or update.effective_user.first_name or "Unknown"
        record_user_activity(user_id, username, "payment")
        date_str = until.strftime('%d.%m.%Y %H:%M')

        kb = [
            [InlineKeyboardButton("🃏 START ANALYZING", callback_data="start_analyzing")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
        ]
        await update.message.reply_text(
            f"🎉 Payment Successful!\n\n"
            f"✅ Your {PREMIUM_DAYS}-day Premium subscription is now active!\n"
            f"📅 Expires: {date_str}\n\n"
            f"🔓 All premium features are unlocked.\n"
            f"Enjoy unlimited access!",
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
            [InlineKeyboardButton("🔄 Refresh", callback_data="signals")],
            [InlineKeyboardButton("🃏 START ANALYZING", callback_data="start_analyzing")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
        ]
        await msg.edit_text(signals_text, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Signals error: {e}")
        await msg.edit_text(f"❌ Error fetching market data: {str(e)[:200]}")


# ==================== ADMIN PANEL ====================

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("⛔ Access denied.")
        return
    stats = get_admin_stats()
    text = _build_admin_panel_text(stats)
    kb = _build_admin_keyboard()
    await update.message.reply_text(text, reply_markup=kb, disable_web_page_preview=True)


def _build_admin_panel_text(stats: dict) -> str:
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
        f"📈 WEEKLY TREND\n"
        f"{stats['week_trend']}\n\n"
        f"🕐 Updated: {now}"
    )


def _build_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh Stats", callback_data="admin_refresh")],
        [InlineKeyboardButton("👥 Recent Users", callback_data="admin_users")],
        [InlineKeyboardButton("💎 Premium Users", callback_data="admin_premium_list")],
        [InlineKeyboardButton("📊 Detailed Analytics", callback_data="admin_analytics")],
        [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast_info")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
    ])


def _build_recent_users_text(stats: dict) -> str:
    text = "👥 RECENT USERS (Last Active)\n━━━━━━━━━━━━━━━━━━━━\n\n"
    if not stats["recent_users"]:
        text += "No users yet."
        return text
    for i, user in enumerate(stats["recent_users"], 1):
        badge = "💎" if user["premium"] else "⬜"
        promo = "🎁" if user["promo_used"] else ""
        la = user.get("last_active", "")
        if la:
            try:
                la = datetime.fromisoformat(la).strftime("%d.%m %H:%M")
            except Exception:
                la = "N/A"
        text += f"{i}. {badge} @{user['username']} {promo}\n   ID: {user['id']} | Analyses: {user['analyses']}\n   Last: {la}\n\n"
    return text


def _build_premium_users_text(stats: dict) -> str:
    data = load_user_data()
    now = datetime.now()
    text = "💎 PREMIUM USERS\n━━━━━━━━━━━━━━━━━━━━\n\n"
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

    text = "📊 DETAILED ANALYTICS\n━━━━━━━━━━━━━━━━━━━━\n\n📅 DAILY BREAKDOWN (Last 7 Days)\n\n"
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
    promo_users = sum(1 for k, v in data.items() if not k.startswith("__") and v.get("promo_used"))
    paid_users = stats_data.get("total_payments", 0)

    text += f"\n💰 CONVERSION\n"
    if total_users > 0:
        text += f"├ Promo Rate: {(promo_users / total_users) * 100:.1f}% ({promo_users}/{total_users})\n"
        text += f"└ Paid Rate: {(paid_users / total_users) * 100:.1f}% ({paid_users}/{total_users})\n"
    else:
        text += "├ No data yet\n"

    revenue = paid_users * 13.99
    text += f"\n💵 ESTIMATED REVENUE\n└ ~${revenue:.2f} ({paid_users} payment(s))\n"
    text += f"\n🕐 Generated: {now.strftime('%d.%m.%Y %H:%M:%S')}"
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


# ==================== CALLBACK HANDLER ====================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # ===== HOME =====
    if query.data == "home":
        premium = get_user_premium_status(user_id)
        text = build_start_text(premium)
        kb = build_start_keyboard(premium["is_premium"])
        await query.edit_message_text(text, reply_markup=kb, disable_web_page_preview=True)

    # ===== START ANALYZING (new flow) =====
    elif query.data == "start_analyzing":
        premium = get_user_premium_status(user_id)
        paywall = _check_premium_access(premium)
        if paywall:
            kb = [
                [InlineKeyboardButton("💎 Buy Premium - ~$13.99", callback_data="buy_premium")],
                [InlineKeyboardButton("🎁 Promo Code", callback_data="promo_info")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
            ]
            await query.edit_message_text(paywall, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return

        await query.edit_message_text(
            "🃏 START ANALYZING\n\n"
            "Type a Solana memecoin address below:\n\n"
            "Example:\n"
            "So11111111111111111111111111111111111111112",
            disable_web_page_preview=True,
        )
        context.user_data["waiting_for_token"] = True
        context.user_data["token_flow"] = "choose_action"

    # ===== TOKEN ACTION CHOICES =====
    elif query.data == "action_analysis":
        token_address = context.user_data.get("current_token_address")
        if not token_address:
            await query.edit_message_text("⚠️ Token address lost. Please start again.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="home")]]))
            return

        await query.edit_message_text(
            "⏳ Analysis in progress...\n\n"
            "🔄 Fetching DexScreener data...\n"
            "🔄 Running RugCheck security scan...\n"
            "🔄 Analyzing whale & holder data...\n"
            "🔄 Generating comprehensive report...",
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
                [InlineKeyboardButton("📈 DexScreener", url=dex_url)],
                [InlineKeyboardButton("⏰ Set Alarm", callback_data="action_alarm")],
                [InlineKeyboardButton("🐋 Whale Alert", callback_data="action_whale")],
                [InlineKeyboardButton("🃏 New Analysis", callback_data="start_analyzing")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
            ]
            reply_markup = InlineKeyboardMarkup(kb)

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

    # ===== SET PRICE ALARM =====
    elif query.data == "action_alarm":
        token_address = context.user_data.get("current_token_address")
        token_name = context.user_data.get("current_token_name", "Unknown")
        token_symbol = context.user_data.get("current_token_symbol", "???")

        if not token_address:
            await query.edit_message_text("⚠️ Token address lost. Please start again.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="home")]]))
            return

        kb = [
            [InlineKeyboardButton("📈 Price Goes Above", callback_data="alarm_price_above")],
            [InlineKeyboardButton("📉 Price Goes Below", callback_data="alarm_price_below")],
            [InlineKeyboardButton("🟢 % Price Increase", callback_data="alarm_pct_up")],
            [InlineKeyboardButton("🔴 % Price Decrease", callback_data="alarm_pct_down")],
            [InlineKeyboardButton("◀️ Back", callback_data="token_actions")],
        ]

        current_price = context.user_data.get("current_token_price", "N/A")
        await query.edit_message_text(
            f"⏰ SET PRICE ALARM\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Token: ${token_symbol} ({token_name})\n"
            f"Current Price: ${current_price}\n\n"
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
            f"⏰ {prompt}\n\n"
            f"Type the value below:",
            disable_web_page_preview=True,
        )

    # ===== WHALE ALERT =====
    elif query.data == "action_whale":
        token_address = context.user_data.get("current_token_address")
        token_name = context.user_data.get("current_token_name", "Unknown")
        token_symbol = context.user_data.get("current_token_symbol", "???")

        if not token_address:
            await query.edit_message_text("⚠️ Token address lost. Please start again.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="home")]]))
            return

        result = add_whale_alert(user_id, token_address, token_name, token_symbol)

        if "error" in result:
            kb = [[InlineKeyboardButton("◀️ Back", callback_data="token_actions")], [InlineKeyboardButton("🏠 Main Menu", callback_data="home")]]
            await query.edit_message_text(f"⚠️ {result['error']}", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
        else:
            kb = [
                [InlineKeyboardButton("🐋 My Whale Alerts", callback_data="my_whale_alerts")],
                [InlineKeyboardButton("🃏 New Analysis", callback_data="start_analyzing")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
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
            [InlineKeyboardButton("🔍 Start Analysis", callback_data="action_analysis")],
            [InlineKeyboardButton("⏰ Set Price Alarm", callback_data="action_alarm")],
            [InlineKeyboardButton("🐋 Whale Alert", callback_data="action_whale")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
        ]
        await query.edit_message_text(
            f"🃏 TOKEN: ${token_symbol} ({token_name})\n"
            f"💰 Price: ${token_price}\n\n"
            f"What would you like to do?",
            reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
        )

    # ===== MY ALARMS =====
    elif query.data == "my_alarms":
        alarms = get_user_alarms(user_id)
        if not alarms:
            kb = [
                [InlineKeyboardButton("🃏 START ANALYZING", callback_data="start_analyzing")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
            ]
            await query.edit_message_text("⏰ MY ALARMS\n━━━━━━━━━━━━━━━━━━━━\n\nNo active alarms.\n\nTo set an alarm, analyze a token first.", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
        else:
            text = "⏰ MY ALARMS\n━━━━━━━━━━━━━━━━━━━━\n\n"
            for a in alarms:
                text += f"#{a['id']} {format_alarm_text(a)}\n"
            text += f"\nTotal: {len(alarms)} active alarm(s)"

            kb = [
                [InlineKeyboardButton("🗑 Delete All Alarms", callback_data="delete_all_alarms")],
                [InlineKeyboardButton("🔄 Refresh", callback_data="my_alarms")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    elif query.data == "delete_all_alarms":
        count = delete_all_alarms(user_id)
        kb = [[InlineKeyboardButton("🏠 Main Menu", callback_data="home")]]
        await query.edit_message_text(f"🗑 Deleted {count} alarm(s).", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    # ===== MY WHALE ALERTS =====
    elif query.data == "my_whale_alerts":
        alerts = get_user_whale_alerts(user_id)
        if not alerts:
            kb = [
                [InlineKeyboardButton("🃏 START ANALYZING", callback_data="start_analyzing")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
            ]
            await query.edit_message_text("🐋 MY WHALE ALERTS\n━━━━━━━━━━━━━━━━━━━━\n\nNo active whale alerts.\n\nTo set a whale alert, analyze a token first.", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
        else:
            text = "🐋 MY WHALE ALERTS\n━━━━━━━━━━━━━━━━━━━━\n\n"
            for a in alerts:
                text += f"#{a['id']} ${a['token_symbol']} — {a['token_name']}\n"
            text += f"\nTotal: {len(alerts)} active whale alert(s)\nChecking every 3 minutes."

            kb = [
                [InlineKeyboardButton("🗑 Delete All Whale Alerts", callback_data="delete_all_whale_alerts")],
                [InlineKeyboardButton("🔄 Refresh", callback_data="my_whale_alerts")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    elif query.data == "delete_all_whale_alerts":
        count = delete_all_whale_alerts(user_id)
        kb = [[InlineKeyboardButton("🏠 Main Menu", callback_data="home")]]
        await query.edit_message_text(f"🗑 Deleted {count} whale alert(s).", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    # ===== SIGNALS =====
    elif query.data == "signals":
        premium = get_user_premium_status(user_id)
        paywall = _check_premium_access(premium)
        if paywall:
            kb = [
                [InlineKeyboardButton("💎 Buy Premium - ~$13.99", callback_data="buy_premium")],
                [InlineKeyboardButton("🎁 Promo Code", callback_data="promo_info")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
            ]
            await query.edit_message_text(paywall, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return
        await query.edit_message_text("⏳ Loading market data...", disable_web_page_preview=True)
        await _send_signals(query.message, user_id)

    # ===== PREMIUM =====
    elif query.data == "premium":
        premium = get_user_premium_status(user_id)
        text = _build_premium_text(premium)
        kb = _build_premium_keyboard(premium)
        await query.edit_message_text(text, reply_markup=kb, disable_web_page_preview=True)

    elif query.data == "buy_premium":
        await send_premium_invoice(query, context)

    elif query.data == "promo_info":
        premium = get_user_premium_status(user_id)
        if premium["is_premium"]:
            kb = [[InlineKeyboardButton("🏠 Main Menu", callback_data="home")]]
            await query.edit_message_text("✅ You already have an active premium subscription!", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return
        if has_used_promo(user_id):
            kb = [
                [InlineKeyboardButton("💎 Buy Premium - ~$13.99", callback_data="buy_premium")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
            ]
            await query.edit_message_text(
                "⚠️ You have already used your free trial.\n\n"
                "Each user can only use the promo code once.\n"
                "To continue using kodark.io, please purchase Premium.",
                reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
            )
            return
        promo_display = f"/{PROMO_CODE}" if PROMO_CODE else "/promo"
        kb = [[InlineKeyboardButton("🏠 Main Menu", callback_data="home")]]
        await query.edit_message_text(
            f"🎁 FREE TRIAL\n\n"
            f"Get a {PROMO_DAYS}-day free trial to unlock all premium features!\n\n"
            f"👉 Just type: {promo_display}\n\n"
            f"This will activate {PROMO_DAYS} days of full access including:\n"
            f"🔍 Unlimited token analysis\n"
            f"🤖 AI-powered reports\n"
            f"🐋 Whale alert notifications\n"
            f"⏰ Price alarm system\n\n"
            f"⚠️ Each user can only use the promo code once.",
            reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
        )

    # ===== ROADMAP =====
    elif query.data == "roadmap":
        kb = [[InlineKeyboardButton("🏠 Main Menu", callback_data="home")]]
        await query.edit_message_text(
            "🗺 ROADMAP - Upcoming Features\n\n"
            "We are constantly working to make kodark.io\n"
            "the best Solana intelligence tool.\n\n"
            "🔜 Coming Soon:\n\n"
            "🔔 Whale Alert Notifications ✅ LIVE\n"
            "Real-time push alerts when whales buy or sell.\n\n"
            "⏰ Price Alarm System ✅ LIVE\n"
            "Set custom price targets and get notified.\n\n"
            "🌐 Multi-Language Support\n"
            "Full support for Turkish, Spanish, Chinese and more.\n\n"
            "👥 Referral System\n"
            "Invite friends and earn free premium days.\n\n"
            "📊 Portfolio Tracker\n"
            "Track your Solana wallet holdings and PnL.\n\n"
            "🤖 Auto-Sniper Alerts\n"
            "Get notified about new token launches.\n\n"
            "📉 Advanced Charting\n"
            "Interactive price charts inside Telegram.\n\n"
            "🛡 Watchlist\n"
            "Save favorite tokens and get daily reports.\n\n"
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
        await query.edit_message_text(_build_admin_panel_text(stats), reply_markup=_build_admin_keyboard(), disable_web_page_preview=True)

    elif query.data == "admin_users":
        if user_id != ADMIN_USER_ID:
            return
        stats = get_admin_stats()
        kb = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="admin_users")],
            [InlineKeyboardButton("◀️ Back to Panel", callback_data="admin_refresh")],
        ]
        await query.edit_message_text(_build_recent_users_text(stats), reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    elif query.data == "admin_premium_list":
        if user_id != ADMIN_USER_ID:
            return
        stats = get_admin_stats()
        kb = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="admin_premium_list")],
            [InlineKeyboardButton("◀️ Back to Panel", callback_data="admin_refresh")],
        ]
        await query.edit_message_text(_build_premium_users_text(stats), reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    elif query.data == "admin_analytics":
        if user_id != ADMIN_USER_ID:
            return
        kb = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="admin_analytics")],
            [InlineKeyboardButton("◀️ Back to Panel", callback_data="admin_refresh")],
        ]
        await query.edit_message_text(_build_analytics_text(), reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    elif query.data == "admin_broadcast_info":
        if user_id != ADMIN_USER_ID:
            return
        kb = [[InlineKeyboardButton("◀️ Back to Panel", callback_data="admin_refresh")]]
        await query.edit_message_text(
            "📢 BROADCAST MESSAGE\n━━━━━━━━━━━━━━━━━━━━\n\n"
            "Send a broadcast to all users:\n\n"
            "Use the command:\n/broadcast Your message here\n\n"
            "This will send your message to all registered users.",
            reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
        )


# ==================== MESSAGE HANDLER ====================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or "Unknown"
    record_user_activity(user_id, username, "message")
    text = update.message.text.strip()

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
            kb = [[InlineKeyboardButton("⏰ Try Again", callback_data="action_alarm")], [InlineKeyboardButton("🏠 Main Menu", callback_data="home")]]
            await update.message.reply_text("⚠️ Invalid value. Please enter a valid number.", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return

        result = add_price_alarm(user_id, token_address, token_name, token_symbol, alarm_type, value, current_price)

        if "error" in result:
            kb = [[InlineKeyboardButton("🏠 Main Menu", callback_data="home")]]
            await update.message.reply_text(f"⚠️ {result['error']}", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
        else:
            alarm = result["alarm"]
            kb = [
                [InlineKeyboardButton("⏰ My Alarms", callback_data="my_alarms")],
                [InlineKeyboardButton("🃏 New Analysis", callback_data="start_analyzing")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
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

        premium = get_user_premium_status(user_id)
        paywall = _check_premium_access(premium)
        if paywall:
            kb = [
                [InlineKeyboardButton("💎 Buy Premium - ~$13.99", callback_data="buy_premium")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
            ]
            await update.message.reply_text(paywall, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return

        token_address = text

        if len(token_address) < 32 or len(token_address) > 50:
            await update.message.reply_text(
                "⚠️ Invalid token address. Please send a valid Solana memecoin address.\n"
                "Try again with START ANALYZING.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🃏 START ANALYZING", callback_data="start_analyzing")]]),
                disable_web_page_preview=True,
            )
            return

        # Fetch token info to show action choices
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

            # Store in context for later use
            context.user_data["current_token_address"] = token_address
            context.user_data["current_token_name"] = token_name
            context.user_data["current_token_symbol"] = token_symbol
            context.user_data["current_token_price"] = price_usd
            context.user_data["current_token_price_float"] = float(price_usd) if price_usd else 0

            kb = [
                [InlineKeyboardButton("🔍 Start Analysis", callback_data="action_analysis")],
                [InlineKeyboardButton("⏰ Set Price Alarm", callback_data="action_alarm")],
                [InlineKeyboardButton("🐋 Whale Alert", callback_data="action_whale")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
            ]

            mcap_str = f"${mcap:,.0f}" if mcap > 0 else "N/A"

            await loading_msg.edit_text(
                f"🃏 TOKEN FOUND\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📌 {token_name} (${token_symbol})\n"
                f"💰 Price: ${price_usd}\n"
                f"📊 Market Cap: {mcap_str}\n"
                f"📈 24h: {change_emoji} {change_24h:+.2f}%\n\n"
                f"What would you like to do?",
                reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
            )

        except Exception as e:
            logger.error(f"Token fetch error: {e}")
            await loading_msg.edit_text(f"❌ Error: {str(e)[:200]}", disable_web_page_preview=True)
        return

    # ===== AUTO-DETECT TOKEN ADDRESS =====
    if len(text) >= 32 and len(text) <= 50 and text.isalnum():
        premium = get_user_premium_status(user_id)
        paywall = _check_premium_access(premium)
        if paywall:
            kb = [
                [InlineKeyboardButton("💎 Buy Premium - ~$13.99", callback_data="buy_premium")],
                [InlineKeyboardButton("🎁 Promo Code", callback_data="promo_info")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
            ]
            await update.message.reply_text(paywall, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return

        context.user_data["waiting_for_token"] = True
        await handle_message(update, context)
    else:
        kb = [[InlineKeyboardButton("🏠 Main Menu", callback_data="home")]]
        await update.message.reply_text(
            "👋 Need help?\n\n"
            "🃏 /start - Main Menu\n"
            "📖 /help - Help Guide\n"
            "💎 /premium - Premium Status\n\n"
            "Or just send a Solana memecoin address!",
            reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
        )


# ==================== BACKGROUND MONITORING ====================

async def background_price_check(app):
    """Background task: check price alarms every 2 minutes."""
    while True:
        try:
            await asyncio.sleep(120)  # 2 minutes

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
                    await asyncio.sleep(1)  # Rate limiting
                except Exception as e:
                    logger.error(f"Price check error for {token_addr}: {e}")

            if not current_prices:
                continue

            triggered = check_alarms(current_prices)

            for t in triggered:
                try:
                    alarm = t["alarm"]
                    current_price = t["current_price"]
                    user_id = t["user_id"]

                    # Check if user still has premium
                    user_premium = get_user_premium_status(user_id)
                    if not user_premium["is_premium"]:
                        logger.info(f"Skipping alarm for non-premium user {user_id}")
                        continue

                    text = (
                        f"🔔 PRICE ALARM TRIGGERED!\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"{format_alarm_text(alarm)}\n\n"
                        f"💰 Current Price: ${current_price:,.8f}\n"
                        f"📅 Set on: {alarm.get('created_at', 'N/A')[:16]}\n\n"
                        f"⚡ This alarm has been deactivated."
                    )

                    await app.bot.send_message(chat_id=user_id, text=text, disable_web_page_preview=True)
                except Exception as e:
                    logger.error(f"Alarm notification error: {e}")

        except Exception as e:
            logger.error(f"Background price check error: {e}")


async def background_whale_check(app):
    """Background task: check whale activity every 3 minutes."""
    while True:
        try:
            await asyncio.sleep(180)  # 3 minutes

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
                                # Check if user still has premium
                                uid_premium = get_user_premium_status(uid)
                                if not uid_premium["is_premium"]:
                                    logger.info(f"Skipping whale alert for non-premium user {uid}")
                                    continue
                                await app.bot.send_message(chat_id=uid, text=alert_text, disable_web_page_preview=True)
                            except Exception as e:
                                logger.error(f"Whale alert send error for {uid}: {e}")

                    await asyncio.sleep(2)  # Rate limiting
                except Exception as e:
                    logger.error(f"Whale check error for {token_addr}: {e}")

        except Exception as e:
            logger.error(f"Background whale check error: {e}")


async def post_init(app):
    """Start background tasks after bot initialization."""
    asyncio.create_task(background_price_check(app))
    asyncio.create_task(background_whale_check(app))
    logger.info("Background monitoring tasks started.")


# ==================== MAIN ====================

def main():
    logger.info("kodark.io Bot starting...")

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("premium", premium_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    if PROMO_CODE:
        app.add_handler(CommandHandler(PROMO_CODE, promo_command))

    # Payment handlers
    app.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))

    # Callback & message handlers
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started successfully! Polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
