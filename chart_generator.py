"""
Advanced Charting Module for kodark.io Bot
Generates price charts and visual analytics for Solana tokens.
Uses matplotlib to create professional-looking charts sent as images in Telegram.
"""

import io
import logging
import requests
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ==================== CHART STYLING ====================

# Dark theme colors matching Telegram dark mode
COLORS = {
    "bg": "#0d1117",
    "panel": "#161b22",
    "grid": "#21262d",
    "text": "#c9d1d9",
    "text_dim": "#8b949e",
    "green": "#3fb950",
    "red": "#f85149",
    "blue": "#58a6ff",
    "purple": "#bc8cff",
    "yellow": "#d29922",
    "orange": "#f0883e",
    "cyan": "#39d353",
    "white": "#ffffff",
}


def _apply_dark_theme():
    """Apply dark theme to matplotlib."""
    plt.rcParams.update({
        'figure.facecolor': COLORS["bg"],
        'axes.facecolor': COLORS["panel"],
        'axes.edgecolor': COLORS["grid"],
        'axes.labelcolor': COLORS["text"],
        'text.color': COLORS["text"],
        'xtick.color': COLORS["text_dim"],
        'ytick.color': COLORS["text_dim"],
        'grid.color': COLORS["grid"],
        'grid.alpha': 0.3,
        'font.size': 10,
        'font.family': 'sans-serif',
    })


# ==================== DATA FETCHING ====================

def _fetch_ohlcv_data(pair_address: str, timeframe: str = "15m") -> list:
    """
    Fetch OHLCV candle data from DexScreener.
    Timeframe options: 1m, 5m, 15m, 1h, 4h, 1d
    """
    try:
        # DexScreener doesn't have a public candle API, so we'll use price history
        # from the pair data and construct a simplified chart
        url = f"https://api.dexscreener.com/latest/dex/pairs/solana/{pair_address}"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if not data.get("pair"):
            return []

        pair = data["pair"]
        return pair

    except Exception as e:
        logger.error(f"OHLCV fetch error: {e}")
        return []


def _build_price_points(token_data: dict) -> dict:
    """
    Build price point data from available token metrics.
    Since DexScreener doesn't provide historical candles publicly,
    we reconstruct a visual representation from available timeframe data.
    """
    price = float(token_data.get("price_usd", 0) or 0)
    if price == 0:
        return None

    change_5m = float(token_data.get("price_change_5m", 0) or 0)
    change_1h = float(token_data.get("price_change_1h", 0) or 0)
    change_6h = float(token_data.get("price_change_6h", 0) or 0)
    change_24h = float(token_data.get("price_change_24h", 0) or 0)

    now = datetime.now()

    # Calculate historical prices from percentage changes
    price_24h_ago = price / (1 + change_24h / 100) if change_24h != -100 else price
    price_6h_ago = price / (1 + change_6h / 100) if change_6h != -100 else price
    price_1h_ago = price / (1 + change_1h / 100) if change_1h != -100 else price
    price_5m_ago = price / (1 + change_5m / 100) if change_5m != -100 else price

    # Build data points
    points = [
        {"time": now - timedelta(hours=24), "price": price_24h_ago},
        {"time": now - timedelta(hours=18), "price": price_24h_ago + (price_6h_ago - price_24h_ago) * 0.33},
        {"time": now - timedelta(hours=12), "price": price_24h_ago + (price_6h_ago - price_24h_ago) * 0.67},
        {"time": now - timedelta(hours=6), "price": price_6h_ago},
        {"time": now - timedelta(hours=3), "price": price_6h_ago + (price_1h_ago - price_6h_ago) * 0.6},
        {"time": now - timedelta(hours=1), "price": price_1h_ago},
        {"time": now - timedelta(minutes=30), "price": price_1h_ago + (price_5m_ago - price_1h_ago) * 0.5},
        {"time": now - timedelta(minutes=5), "price": price_5m_ago},
        {"time": now, "price": price},
    ]

    # Volume data
    volume_24h = float(token_data.get("volume_24h", 0) or 0)
    volume_6h = float(token_data.get("volume_6h", 0) or 0)
    volume_1h = float(token_data.get("volume_1h", 0) or 0)

    return {
        "points": points,
        "current_price": price,
        "change_24h": change_24h,
        "volume_24h": volume_24h,
        "volume_6h": volume_6h,
        "volume_1h": volume_1h,
        "name": token_data.get("name", "Unknown"),
        "symbol": token_data.get("symbol", "???"),
        "market_cap": float(token_data.get("market_cap", 0) or 0),
        "liquidity": float(token_data.get("liquidity_usd", 0) or 0),
    }


# ==================== CHART GENERATION ====================

def generate_price_chart(token_data: dict) -> io.BytesIO:
    """
    Generate a professional price chart image from token data.
    Returns a BytesIO object containing the PNG image.
    """
    _apply_dark_theme()

    price_data = _build_price_points(token_data)
    if not price_data:
        return None

    points = price_data["points"]
    times = [p["time"] for p in points]
    prices = [p["price"] for p in points]

    # Create figure with 2 subplots (price + volume)
    fig, (ax1, ax2) = plt.subplots(
        2, 1,
        figsize=(10, 7),
        gridspec_kw={'height_ratios': [3, 1]},
        sharex=True
    )
    fig.patch.set_facecolor(COLORS["bg"])

    # ===== PRICE CHART =====
    change_24h = price_data["change_24h"]
    line_color = COLORS["green"] if change_24h >= 0 else COLORS["red"]
    fill_color = COLORS["green"] if change_24h >= 0 else COLORS["red"]

    # Plot price line with gradient fill
    ax1.plot(times, prices, color=line_color, linewidth=2.5, zorder=5)
    ax1.fill_between(times, prices, min(prices) * 0.99, alpha=0.15, color=fill_color, zorder=2)

    # Add current price marker
    ax1.scatter([times[-1]], [prices[-1]], color=line_color, s=80, zorder=10, edgecolors=COLORS["white"], linewidth=1.5)

    # Price annotations
    current_price = price_data["current_price"]
    ax1.annotate(
        f'${current_price:,.8f}' if current_price < 0.01 else f'${current_price:,.4f}' if current_price < 1 else f'${current_price:,.2f}',
        xy=(times[-1], prices[-1]),
        xytext=(10, 15),
        textcoords='offset points',
        fontsize=12,
        fontweight='bold',
        color=line_color,
        bbox=dict(boxstyle='round,pad=0.3', facecolor=COLORS["panel"], edgecolor=line_color, alpha=0.9),
    )

    # Grid and styling
    ax1.grid(True, alpha=0.2, linestyle='--')
    ax1.set_facecolor(COLORS["panel"])

    # Title
    symbol = price_data["symbol"]
    name = price_data["name"]
    change_str = f"+{change_24h:.1f}%" if change_24h >= 0 else f"{change_24h:.1f}%"
    change_color = COLORS["green"] if change_24h >= 0 else COLORS["red"]

    title_text = f"{name} (${symbol})"
    ax1.set_title(title_text, fontsize=16, fontweight='bold', color=COLORS["white"], pad=15, loc='left')

    # Add 24h change as subtitle
    ax1.text(
        0.99, 1.02, f"24h: {change_str}",
        transform=ax1.transAxes,
        fontsize=13, fontweight='bold',
        color=change_color,
        ha='right', va='bottom'
    )

    # Y-axis formatting
    if current_price < 0.001:
        ax1.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.8f'))
    elif current_price < 1:
        ax1.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.6f'))
    elif current_price < 100:
        ax1.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.4f'))
    else:
        ax1.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f'))

    ax1.set_ylabel('Price (USD)', fontsize=11, color=COLORS["text_dim"])

    # ===== VOLUME BARS =====
    vol_24h = price_data["volume_24h"]
    vol_6h = price_data["volume_6h"]
    vol_1h = price_data["volume_1h"]

    # Create volume bars at key time points
    vol_times = [
        times[0], times[1], times[2], times[3],
        times[4], times[5], times[6], times[7], times[8]
    ]
    # Distribute volume across bars (approximation)
    vol_remaining = vol_24h - vol_6h
    vol_6h_only = vol_6h - vol_1h
    vol_bars = [
        vol_remaining * 0.15, vol_remaining * 0.2, vol_remaining * 0.25, vol_remaining * 0.4,
        vol_6h_only * 0.3, vol_6h_only * 0.7,
        vol_1h * 0.3, vol_1h * 0.3, vol_1h * 0.4
    ]
    # Ensure no negative volumes
    vol_bars = [max(0, v) for v in vol_bars]

    # Color bars based on price movement
    bar_colors = []
    for i in range(len(prices)):
        if i == 0:
            bar_colors.append(COLORS["green"])
        elif prices[i] >= prices[i-1]:
            bar_colors.append(COLORS["green"])
        else:
            bar_colors.append(COLORS["red"])

    bar_width = timedelta(hours=2)
    ax2.bar(vol_times, vol_bars, width=bar_width, color=bar_colors, alpha=0.6, zorder=3)

    ax2.set_facecolor(COLORS["panel"])
    ax2.grid(True, alpha=0.2, linestyle='--')
    ax2.set_ylabel('Volume', fontsize=11, color=COLORS["text_dim"])

    # Volume Y-axis formatting
    def format_volume(x, pos):
        if x >= 1_000_000:
            return f'${x/1_000_000:.1f}M'
        elif x >= 1_000:
            return f'${x/1_000:.0f}K'
        else:
            return f'${x:.0f}'

    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(format_volume))

    # X-axis formatting
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax2.xaxis.set_major_locator(mdates.HourLocator(interval=4))
    plt.xticks(rotation=0)

    # ===== INFO BOX =====
    mcap = price_data["market_cap"]
    liq = price_data["liquidity"]

    info_text = (
        f"MCap: ${mcap:,.0f}  |  "
        f"Liq: ${liq:,.0f}  |  "
        f"24h Vol: ${vol_24h:,.0f}"
    )
    fig.text(
        0.5, 0.01, info_text,
        ha='center', fontsize=10,
        color=COLORS["text_dim"],
        style='italic'
    )

    # Watermark
    fig.text(
        0.99, 0.01, "kodark.io",
        ha='right', fontsize=9,
        color=COLORS["text_dim"],
        alpha=0.5
    )

    plt.tight_layout()
    plt.subplots_adjust(bottom=0.08, hspace=0.05)

    # Save to BytesIO
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                facecolor=COLORS["bg"], edgecolor='none')
    buf.seek(0)
    plt.close(fig)

    return buf


def generate_multi_token_chart(tokens_data: list) -> io.BytesIO:
    """
    Generate a comparison chart for multiple tokens.
    tokens_data: list of token_data dicts
    """
    if not tokens_data or len(tokens_data) < 2:
        return None

    _apply_dark_theme()

    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor(COLORS["bg"])
    ax.set_facecolor(COLORS["panel"])

    chart_colors = [COLORS["green"], COLORS["blue"], COLORS["purple"], COLORS["yellow"], COLORS["orange"]]

    for i, token_data in enumerate(tokens_data[:5]):
        price_data = _build_price_points(token_data)
        if not price_data:
            continue

        points = price_data["points"]
        times = [p["time"] for p in points]
        # Normalize prices to percentage change from start
        base_price = points[0]["price"]
        if base_price > 0:
            pct_changes = [(p["price"] / base_price - 1) * 100 for p in points]
        else:
            pct_changes = [0] * len(points)

        color = chart_colors[i % len(chart_colors)]
        symbol = price_data["symbol"]
        ax.plot(times, pct_changes, color=color, linewidth=2, label=f"${symbol}")

    ax.axhline(y=0, color=COLORS["text_dim"], linewidth=0.5, linestyle='--', alpha=0.5)
    ax.grid(True, alpha=0.2, linestyle='--')
    ax.set_title("24h Performance Comparison", fontsize=14, fontweight='bold', color=COLORS["white"], pad=10)
    ax.set_ylabel("Change (%)", fontsize=11, color=COLORS["text_dim"])
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax.legend(loc='upper left', fontsize=10, facecolor=COLORS["panel"], edgecolor=COLORS["grid"])

    fig.text(0.99, 0.01, "kodark.io", ha='right', fontsize=9, color=COLORS["text_dim"], alpha=0.5)

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                facecolor=COLORS["bg"], edgecolor='none')
    buf.seek(0)
    plt.close(fig)

    return buf
