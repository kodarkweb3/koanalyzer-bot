"""
kodark.io - Solana Memecoins Analyzer Bot v4.0
Whale Watch | Holder Analysis | Risk Assessment | Price Alarms
Auto-Sniper Alerts | Multi-Language | Advanced Charting
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

PREMIUM_PRICE_STARS = 550  # ~$7.99
PREMIUM_DAYS = 30
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))

# Free tier limits
FREE_ANALYSIS_LIMIT = 3
FREE_ALARM_LIMIT = 3

# ==================== PERSISTENT DATA STORAGE ====================
# Use DATA_DIR env variable for Railway volume persistence
# Set DATA_DIR=/data in Railway and mount a volume at /data

DATA_DIR = os.getenv("DATA_DIR", ".")
os.makedirs(DATA_DIR, exist_ok=True)

DATA_FILE = os.path.join(DATA_DIR, "user_data.json")
FEEDBACK_FILE = os.path.join(DATA_DIR, "feedback.json")


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


def load_feedback() -> list:
    try:
        if os.path.exists(FEEDBACK_FILE):
            with open(FEEDBACK_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Feedback load error: {e}")
    return []


def save_feedback(feedbacks: list):
    try:
        with open(FEEDBACK_FILE, "w") as f:
            json.dump(feedbacks, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Feedback save error: {e}")


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
        f"💰 Only ~$7.99/month ({PREMIUM_PRICE_STARS} Stars)\n\n"
        f"👇 Tap below to upgrade:"
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
        f"💰 Only ~$7.99/month ({PREMIUM_PRICE_STARS} Stars)\n\n"
        f"👇 Tap below to upgrade:"
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
        f"💰 Only ~$7.99/month ({PREMIUM_PRICE_STARS} Stars)\n\n"
        f"👇 Tap below to upgrade:"
    )


# ==================== START MENU ====================

def build_start_text(premium: dict, lang: str = "en", user_id: int = None) -> str:
    if premium["is_premium"]:
        if premium["remaining"] == "Unlimited":
            status_line = f"{get_text('premium_active', lang)}: {get_text('lifetime', lang)}"
        else:
            status_line = f"{get_text('premium_active', lang)} ({premium['remaining']} left)\n📅 Expires: {premium['until']}"
    else:
        # Show free tier usage
        usage = get_free_usage(user_id) if user_id else {"analyses_left": FREE_ANALYSIS_LIMIT, "alarms_left": FREE_ALARM_LIMIT}
        status_line = (
            f"{get_text('premium_inactive', lang)}\n"
            f"🆓 Free: {usage['analyses_left']}/{FREE_ANALYSIS_LIMIT} analyses | {usage['alarms_left']}/{FREE_ALARM_LIMIT} alarms remaining"
        )

    payment_line = "" if premium["is_premium"] else f"\n💎 Premium: ~$7.99/month ({PREMIUM_PRICE_STARS} Stars)\n"

    text = (
        f"{get_text('start_title', lang)}\n"
        f"\n"
        f"{get_text('start_subtitle', lang)}\n"
        f"\n"
        f"{get_text('features_header', lang)}\n"
        f"{get_text('feature_whale', lang)}\n"
        f"{get_text('feature_risk', lang)}\n"
        f"{get_text('feature_holder', lang)}\n"
        f"{get_text('feature_alarm', lang)}\n"
        f"{get_text('feature_sniper', lang)}\n"
        f"{get_text('feature_chart', lang)}\n"
        f"{get_text('feature_signals', lang)}\n"
        f"\n"
        f"{status_line}"
        f"{payment_line}"
        f"\n"
        f"🔗 x.com/kodarkweb3\n"
        f"🔗 x.com/kodarkio\n"
        f"\n"
        f"{get_text('select_option', lang)}"
    )
    return text


def build_start_keyboard(is_premium: bool, lang: str = "en") -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(get_text('btn_start_analyzing', lang), callback_data="start_analyzing")],
        [InlineKeyboardButton(get_text('btn_market_signals', lang), callback_data="signals")],
        [
            InlineKeyboardButton(get_text('btn_my_alarms', lang), callback_data="my_alarms"),
            InlineKeyboardButton(get_text('btn_whale_alerts', lang), callback_data="my_whale_alerts"),
        ],
        [InlineKeyboardButton(get_text('btn_sniper_alerts', lang), callback_data="sniper_menu")],
        [InlineKeyboardButton(get_text('btn_premium', lang), callback_data="premium")],
        [InlineKeyboardButton("💬 Feedback", callback_data="feedback_start")],
        [InlineKeyboardButton(get_text('btn_language', lang), callback_data="language_menu")],
        [InlineKeyboardButton(get_text('btn_roadmap', lang), callback_data="roadmap")],
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
        "📖 kodark.io Bot - Help Guide\n\n"
        "🚀 Commands:\n\n"
        "/start - Main menu\n"
        "/help - This help guide\n"
        "/premium - Premium status\n"
        "/feedback - Send feedback\n"
        "/admin - Admin panel (admin only)\n\n"
        "🔍 How to Use:\n"
        "1. Tap 'START ANALYZING'\n"
        "2. Enter a Solana memecoin address\n"
        "3. Choose: Analysis, Chart, Price Alarm, or Whale Alert\n\n"
        f"🆓 Free Tier: {FREE_ANALYSIS_LIMIT} analyses + {FREE_ALARM_LIMIT} price alarms\n"
        f"💎 Premium: ~$7.99/month for unlimited access\n\n"
        "🔗 x.com/kodarkweb3\n"
        "🔗 x.com/kodarkio"
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
        usage = get_free_usage(user_id) if user_id else {"analyses_left": FREE_ANALYSIS_LIMIT, "alarms_left": FREE_ALARM_LIMIT}
        return (
            f"💎 PREMIUM STATUS\n\n"
            f"❌ Status: Inactive\n\n"
            f"🆓 Free Tier Remaining:\n"
            f"🔍 Analyses: {usage['analyses_left']}/{FREE_ANALYSIS_LIMIT}\n"
            f"⏰ Alarms: {usage['alarms_left']}/{FREE_ALARM_LIMIT}\n\n"
            f"🔒 Premium features include:\n"
            f"🔍 Unlimited token analysis\n"
            f"🤖 AI-powered reports\n"
            f"🐋 Whale alert notifications\n"
            f"⏰ Unlimited price alarms\n"
            f"🎯 Auto-Sniper alerts\n"
            f"📊 Advanced charts\n"
            f"⚡ Priority support\n\n"
            f"💰 Price: ~$7.99 ({PREMIUM_PRICE_STARS} Telegram Stars)\n"
            f"📅 Duration: {PREMIUM_DAYS} days\n\n"
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
            [InlineKeyboardButton("💎 Buy Premium - ~$7.99", callback_data="buy_premium")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
        ])


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
                    f"Auto-Sniper alerts\n"
                    f"Advanced charts\n"
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
        data = load_user_data()
        user_str = str(user_id)
        if user_str in data:
            data[user_str]["paid_premium"] = True
            save_user_data(data)
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
        [InlineKeyboardButton("📊 Detailed Analytics", callback_data="admin_analytics")],
        [InlineKeyboardButton(fb_label, callback_data="admin_feedback")],
        [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast_info")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
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
                [InlineKeyboardButton("💎 Buy Premium - ~$7.99", callback_data="buy_premium")],
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
            f"{get_text('type_address', lang)}\n"
            f"{usage_hint}\n"
            f"Example:\nSo11111111111111111111111111111111111111112",
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

        # Check analysis access
        paywall = _check_analysis_access(user_id, lang)
        if paywall:
            kb = [
                [InlineKeyboardButton("💎 Buy Premium - ~$7.99", callback_data="buy_premium")],
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
                [InlineKeyboardButton("📈 DexScreener", url=dex_url)],
                [InlineKeyboardButton(get_text('btn_chart', lang), callback_data="action_chart")],
                [InlineKeyboardButton("⏰ Set Alarm", callback_data="action_alarm")],
                [InlineKeyboardButton("🐋 Whale Alert", callback_data="action_whale")],
                [InlineKeyboardButton("🃏 New Analysis", callback_data="start_analyzing")],
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
                [InlineKeyboardButton("💎 Buy Premium - ~$7.99", callback_data="buy_premium")],
                [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
            ]
            await query.edit_message_text(paywall, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return

        token_data = context.user_data.get("current_token_data")
        token_address = context.user_data.get("current_token_address")

        if not token_data or not token_address:
            await query.edit_message_text("⚠️ Token data not found. Please run analysis first.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="home")]]))
            return

        await query.edit_message_text("📊 Generating chart...", disable_web_page_preview=True)

        try:
            chart_buf = generate_price_chart(token_data)
            if chart_buf:
                token_symbol = context.user_data.get("current_token_symbol", "???")
                token_name = context.user_data.get("current_token_name", "Unknown")

                kb = [
                    [InlineKeyboardButton("🔍 Start Analysis", callback_data="action_analysis")],
                    [InlineKeyboardButton("⏰ Set Alarm", callback_data="action_alarm")],
                    [InlineKeyboardButton("🐋 Whale Alert", callback_data="action_whale")],
                    [InlineKeyboardButton("🃏 New Analysis", callback_data="start_analyzing")],
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
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="home")]]),
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
                [InlineKeyboardButton("💎 Buy Premium - ~$7.99", callback_data="buy_premium")],
                [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
            ]
            await query.edit_message_text(paywall, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return

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
                [InlineKeyboardButton("💎 Buy Premium - ~$7.99", callback_data="buy_premium")],
                [InlineKeyboardButton(get_text('btn_back', lang), callback_data="token_actions")],
                [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
            ]
            await query.edit_message_text(paywall, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return

        token_address = context.user_data.get("current_token_address")
        token_name = context.user_data.get("current_token_name", "Unknown")
        token_symbol = context.user_data.get("current_token_symbol", "???")

        if not token_address:
            await query.edit_message_text("⚠️ Token address lost. Please start again.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="home")]]))
            return

        result = add_whale_alert(user_id, token_address, token_name, token_symbol)

        if "error" in result:
            kb = [[InlineKeyboardButton(get_text('btn_back', lang), callback_data="token_actions")], [InlineKeyboardButton("🏠 Main Menu", callback_data="home")]]
            await query.edit_message_text(f"⚠️ {result['error']}", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
        else:
            kb = [
                [InlineKeyboardButton("🐋 My Whale Alerts", callback_data="my_whale_alerts")],
                [InlineKeyboardButton("🃏 New Analysis", callback_data="start_analyzing")],
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
            [InlineKeyboardButton("🔍 Start Analysis", callback_data="action_analysis")],
            [InlineKeyboardButton(get_text('btn_chart', lang), callback_data="action_chart")],
            [InlineKeyboardButton("⏰ Set Price Alarm", callback_data="action_alarm")],
            [InlineKeyboardButton("🐋 Whale Alert", callback_data="action_whale")],
            [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
        ]
        await query.edit_message_text(
            f"🃏 TOKEN: ${token_symbol} ({token_name})\n"
            f"💰 Price: ${token_price}\n\n"
            f"{get_text('what_to_do', lang)}",
            reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True,
        )

    # ===== MY ALARMS =====
    elif query.data == "my_alarms":
        alarms = get_user_alarms(user_id)
        if not alarms:
            kb = [
                [InlineKeyboardButton("🃏 START ANALYZING", callback_data="start_analyzing")],
                [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
            ]
            await query.edit_message_text("⏰ MY ALARMS\n━━━━━━━━━━━━━━━\n\nNo active alarms.\n\nTo set an alarm, analyze a token first.", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
        else:
            text = "⏰ MY ALARMS\n━━━━━━━━━━━━━━━\n\n"
            for a in alarms:
                text += f"#{a['id']} {format_alarm_text(a)}\n"
            text += f"\nTotal: {len(alarms)} active alarm(s)"

            kb = [
                [InlineKeyboardButton("🗑 Delete All Alarms", callback_data="delete_all_alarms")],
                [InlineKeyboardButton("🔄 Refresh", callback_data="my_alarms")],
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
                [InlineKeyboardButton("💎 Buy Premium - ~$7.99", callback_data="buy_premium")],
                [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
            ]
            await query.edit_message_text(paywall, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return

        alerts = get_user_whale_alerts(user_id)
        if not alerts:
            kb = [
                [InlineKeyboardButton("🃏 START ANALYZING", callback_data="start_analyzing")],
                [InlineKeyboardButton(get_text('btn_home', lang), callback_data="home")],
            ]
            await query.edit_message_text("🐋 MY WHALE ALERTS\n━━━━━━━━━━━━━━━\n\nNo active whale alerts.\n\nTo set a whale alert, analyze a token first.", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
        else:
            text = "🐋 MY WHALE ALERTS\n━━━━━━━━━━━━━━━\n\n"
            for a in alerts:
                text += f"#{a['id']} ${a['token_symbol']} — {a['token_name']}\n"
            text += f"\nTotal: {len(alerts)} active whale alert(s)\nChecking every 3 minutes."

            kb = [
                [InlineKeyboardButton("🗑 Delete All Whale Alerts", callback_data="delete_all_whale_alerts")],
                [InlineKeyboardButton("🔄 Refresh", callback_data="my_whale_alerts")],
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
                [InlineKeyboardButton("💎 Buy Premium - ~$7.99", callback_data="buy_premium")],
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
                [InlineKeyboardButton("💎 Buy Premium - ~$7.99", callback_data="buy_premium")],
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
        await send_premium_invoice(query, context)

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
            "💬 Feedback System ✅\n"
            "Send feedback directly to the team.\n\n"
            "━━━━━━━━━━━━━━━\n\n"
            "🔜 COMING SOON\n\n"
            "👥 Referral System\n"
            "Invite friends and earn free premium days.\n\n"
            "🛡 Watchlist & Daily Reports\n"
            "Save favorite tokens and get automated daily summaries.\n\n"
            "🤖 AI Trading Signals\n"
            "Machine learning-based buy/sell signals.\n\n"
            "📱 Mini App Dashboard\n"
            "Full-featured Telegram Mini App with interactive charts.\n\n"
            "🔗 Wallet Connect\n"
            "Connect your Solana wallet for personalized analytics.\n\n"
            "🏆 Leaderboard & Community\n"
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

    elif query.data == "admin_feedback":
        if user_id != ADMIN_USER_ID:
            return
        kb = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="admin_feedback")],
            [InlineKeyboardButton("◀️ Back to Panel", callback_data="admin_refresh")],
        ]
        await query.edit_message_text(_build_feedback_text(), reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

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


# ==================== MESSAGE HANDLER ====================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or "Unknown"
    record_user_activity(user_id, username, "message")
    text = update.message.text.strip()
    lang = get_user_lang(user_id)

    # ===== WAITING FOR FEEDBACK =====
    if context.user_data.get("waiting_for_feedback"):
        context.user_data["waiting_for_feedback"] = False
        add_feedback(user_id, username, text)
        kb = [[InlineKeyboardButton("🏠 Main Menu", callback_data="home")]]
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
            kb = [[InlineKeyboardButton("⏰ Try Again", callback_data="action_alarm")], [InlineKeyboardButton("🏠 Main Menu", callback_data="home")]]
            await update.message.reply_text("⚠️ Invalid value. Please enter a valid number.", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return

        # Check alarm access again before setting
        paywall = _check_alarm_access(user_id, lang)
        if paywall:
            kb = [
                [InlineKeyboardButton("💎 Buy Premium - ~$7.99", callback_data="buy_premium")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
            ]
            await update.message.reply_text(paywall, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return

        result = add_price_alarm(user_id, token_address, token_name, token_symbol, alarm_type, value, current_price)

        if "error" in result:
            kb = [[InlineKeyboardButton("🏠 Main Menu", callback_data="home")]]
            await update.message.reply_text(f"⚠️ {result['error']}", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
        else:
            # Increment alarm count for free tier tracking
            increment_alarm_count(user_id)
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

        # Check analysis access
        paywall = _check_analysis_access(user_id, lang)
        if paywall:
            kb = [
                [InlineKeyboardButton("💎 Buy Premium - ~$7.99", callback_data="buy_premium")],
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
                [InlineKeyboardButton("🔍 Start Analysis", callback_data="action_analysis")],
                [InlineKeyboardButton(get_text('btn_chart', lang), callback_data="action_chart")],
                [InlineKeyboardButton("⏰ Set Price Alarm", callback_data="action_alarm")],
                [InlineKeyboardButton("🐋 Whale Alert", callback_data="action_whale")],
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
                [InlineKeyboardButton("💎 Buy Premium - ~$7.99", callback_data="buy_premium")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
            ]
            await update.message.reply_text(paywall, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
            return

        context.user_data["waiting_for_token"] = True
        await handle_message(update, context)
    else:
        kb = [[InlineKeyboardButton("🏠 Main Menu", callback_data="home")]]
        await update.message.reply_text(
            "👋 Welcome to kodark.io!\n\n"
            "🃏 /start - Main Menu\n"
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


async def post_init(app):
    """Start background tasks after bot initialization."""
    asyncio.create_task(background_price_check(app))
    asyncio.create_task(background_whale_check(app))
    asyncio.create_task(background_sniper_check(app))
    logger.info("Background monitoring tasks started (price, whale, sniper).")


# ==================== MAIN ====================

def main():
    logger.info("kodark.io Bot v4.0 starting...")

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

    logger.info("Bot v4.0 started successfully! Polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
