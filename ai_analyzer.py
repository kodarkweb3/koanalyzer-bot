"""
AI-Powered Token Analysis Engine v2.0
Analyzes Solana token data and generates premium investment reports.
Enhanced with: Smart Money signals, Liquidity Depth analysis, Momentum scoring,
Entry/Exit zones, Comparative market positioning, and Risk-Reward assessment.
"""

import logging
import os
from openai import OpenAI

logger = logging.getLogger(__name__)


def analyze_token(token_data: dict, rug_data: dict) -> str:
    """
    Analyze token data and security info to generate
    a premium-grade professional report.
    """
    try:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if api_key:
            return _ai_analysis(token_data, rug_data, api_key)
    except Exception as e:
        logger.warning(f"AI analysis failed, falling back to rule-based: {e}")

    return _rule_based_analysis(token_data, rug_data)


def _ai_analysis(token_data: dict, rug_data: dict, api_key: str) -> str:
    """Advanced analysis using OpenAI API with enhanced prompting."""
    try:
        client = OpenAI(api_key=api_key)

        # Calculate additional metrics for AI
        liquidity = float(token_data.get('liquidity_usd', 0) or 0)
        volume_24h = float(token_data.get('volume_24h', 0) or 0)
        mcap = float(token_data.get('market_cap', 0) or 0)
        fdv = float(token_data.get('fdv', 0) or 0)

        vol_liq_ratio = volume_24h / liquidity if liquidity > 0 else 0
        mcap_liq_ratio = mcap / liquidity if liquidity > 0 else 0
        circ_ratio = (mcap / fdv * 100) if fdv > 0 else 0

        buys_24h = int(token_data.get('txns_buy_24h', 0) or 0)
        sells_24h = int(token_data.get('txns_sell_24h', 0) or 0)
        buys_1h = int(token_data.get('txns_buy_1h', 0) or 0)
        sells_1h = int(token_data.get('txns_sell_1h', 0) or 0)
        buys_6h = int(token_data.get('txns_buy_6h', 0) or 0)
        sells_6h = int(token_data.get('txns_sell_6h', 0) or 0)

        total_24h = buys_24h + sells_24h
        total_1h = buys_1h + sells_1h
        buy_ratio_24h = (buys_24h / total_24h * 100) if total_24h > 0 else 50
        buy_ratio_1h = (buys_1h / total_1h * 100) if total_1h > 0 else 50

        # Smart money indicator: if 1h buy ratio is significantly higher than 24h
        smart_money_signal = "NEUTRAL"
        if buy_ratio_1h > buy_ratio_24h + 10 and buys_1h > 20:
            smart_money_signal = "ACCUMULATION DETECTED"
        elif buy_ratio_1h < buy_ratio_24h - 10 and sells_1h > 20:
            smart_money_signal = "DISTRIBUTION DETECTED"

        prompt = f"""You are an elite Solana blockchain analyst working for a premium crypto intelligence firm. Generate a comprehensive, data-driven investment report that provides REAL VALUE to traders.

TOKEN DATA:
- Name: {token_data.get('name', 'N/A')} ({token_data.get('symbol', 'N/A')})
- Contract: {token_data.get('address', 'N/A')}
- Price: ${token_data.get('price_usd', '0')}
- Market Cap: ${mcap:,.0f}
- FDV: ${fdv:,.0f}
- Circulation Ratio: {circ_ratio:.1f}%
- Liquidity: ${liquidity:,.0f}
- MCap/Liquidity Ratio: {mcap_liq_ratio:.1f}x
- 24h Volume: ${volume_24h:,.0f}
- 6h Volume: ${float(token_data.get('volume_6h', 0) or 0):,.0f}
- 1h Volume: ${float(token_data.get('volume_1h', 0) or 0):,.0f}
- Vol/Liq Ratio: {vol_liq_ratio:.2f}x
- 5m Change: {token_data.get('price_change_5m', 0)}%
- 1h Change: {token_data.get('price_change_1h', 0)}%
- 6h Change: {token_data.get('price_change_6h', 0)}%
- 24h Change: {token_data.get('price_change_24h', 0)}%
- 24h Buys: {buys_24h} | Sells: {sells_24h} | Buy Ratio: {buy_ratio_24h:.1f}%
- 6h Buys: {buys_6h} | Sells: {sells_6h}
- 1h Buys: {buys_1h} | Sells: {sells_1h} | Buy Ratio: {buy_ratio_1h:.1f}%
- Smart Money Signal: {smart_money_signal}
- Age: {token_data.get('age', 'Unknown')}
- DEX: {token_data.get('dex_id', 'N/A')}
- Total Pairs: {token_data.get('total_pairs', 1)}

SECURITY DATA:
- RugCheck Score: {rug_data.get('risk_score', 'N/A')}
- Risk Level: {rug_data.get('risk_level', 'N/A')}
- Insider Percentage: {rug_data.get('total_insider_pct', 0)}%
- Top 10 Holders: {rug_data.get('total_top10_pct', 'N/A')}%
- Mint Authority: {rug_data.get('mint_authority', 'None')}
- Freeze Authority: {rug_data.get('freeze_authority', 'None')}
- Mutable Metadata: {rug_data.get('is_mutable', 'N/A')}
- Detected Risks: {', '.join([r['name'] + ' (' + r.get('level','') + ')' for r in rug_data.get('risks', [])])}

TOP HOLDERS:
{_format_holders_for_prompt(rug_data.get('top_holders', []))}

Generate a PREMIUM report with these EXACT sections. Use emojis tastefully. Do NOT use markdown bold (asterisks). Write in plain text.

SECTIONS:
1. EXECUTIVE SUMMARY - 2-3 sentence verdict with score, key opportunity/risk, and recommended action
2. MARKET POSITION - Token overview, market cap assessment, FDV vs MCap analysis, circulation ratio meaning
3. LIQUIDITY HEALTH - Liquidity depth analysis, MCap/Liq ratio assessment (healthy <10x, risky >20x), slippage estimation for $1K/$5K/$10K trades
4. VOLUME & MOMENTUM - Multi-timeframe volume analysis, Vol/Liq ratio health, momentum scoring (accelerating/decelerating), volume trend direction
5. PRICE ACTION & ENTRY ZONES - Multi-timeframe price analysis, current trend, suggested entry zone (based on support), take-profit targets, stop-loss level
6. SMART MONEY ANALYSIS - Buy/sell ratio across timeframes, accumulation vs distribution detection, institutional vs retail flow assessment
7. SECURITY AUDIT - Comprehensive rug pull risk, contract authorities analysis, metadata mutability, each detected vulnerability explained
8. WHALE & HOLDER INTELLIGENCE - Top holder concentration risk, insider activity, distribution health score, whale dump probability
9. RISK-REWARD MATRIX - Overall risk score, potential upside, potential downside, risk-reward ratio, position sizing recommendation
10. FINAL VERDICT - Score (X/10), clear BUY/SELL/HOLD recommendation, specific conditions to watch, time horizon

Be extremely analytical and data-driven. Explain WHY each metric matters for the trader's decision. Give specific numbers and actionable insights. This report should feel worth paying for."""

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3500,
            temperature=0.7,
        )

        report = response.choices[0].message.content
        report += "\n\nPowered by kodarkweb3 | For help & collaboration @yms56"
        return report

    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        raise


def _format_holders_for_prompt(holders: list) -> str:
    """Format holder data for AI prompt."""
    if not holders:
        return "No holder data available"
    lines = []
    for i, h in enumerate(holders[:10], 1):
        addr = h.get('address', 'N/A')
        short = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 10 else addr
        insider = " (INSIDER)" if h.get("insider") else ""
        lines.append(f"  #{i}: {short} - {h.get('pct', 0)}%{insider}")
    return "\n".join(lines)


def _rule_based_analysis(token_data: dict, rug_data: dict) -> str:
    """Comprehensive rule-based analysis without API — enhanced v2.0."""

    name = token_data.get("name", "Unknown")
    symbol = token_data.get("symbol", "???")
    price = token_data.get("price_usd", "0")
    address = token_data.get("address", "N/A")
    mcap = float(token_data.get("market_cap", 0) or 0)
    fdv = float(token_data.get("fdv", 0) or 0)
    liquidity = float(token_data.get("liquidity_usd", 0) or 0)
    volume_24h = float(token_data.get("volume_24h", 0) or 0)
    volume_6h = float(token_data.get("volume_6h", 0) or 0)
    volume_1h = float(token_data.get("volume_1h", 0) or 0)
    change_5m = float(token_data.get("price_change_5m", 0) or 0)
    change_1h = float(token_data.get("price_change_1h", 0) or 0)
    change_6h = float(token_data.get("price_change_6h", 0) or 0)
    change_24h = float(token_data.get("price_change_24h", 0) or 0)
    buys_24h = int(token_data.get("txns_buy_24h", 0) or 0)
    sells_24h = int(token_data.get("txns_sell_24h", 0) or 0)
    buys_1h = int(token_data.get("txns_buy_1h", 0) or 0)
    sells_1h = int(token_data.get("txns_sell_1h", 0) or 0)
    buys_6h = int(token_data.get("txns_buy_6h", 0) or 0)
    sells_6h = int(token_data.get("txns_sell_6h", 0) or 0)
    age = token_data.get("age", "Unknown")
    dex = token_data.get("dex_id", "N/A").upper()
    total_pairs = token_data.get("total_pairs", 1)

    risk_score = rug_data.get("risk_score", None)
    risk_level = rug_data.get("risk_level", "UNKNOWN")
    insider_pct = float(rug_data.get("total_insider_pct", 0) or 0)
    top10_pct = float(rug_data.get("total_top10_pct", 0) or 0)
    mint_auth = rug_data.get("mint_authority", None)
    freeze_auth = rug_data.get("freeze_authority", None)
    is_mutable = rug_data.get("is_mutable", None)
    risks = rug_data.get("risks", [])

    # ==================== ADVANCED CALCULATIONS ====================

    # Ratios
    vol_liq_ratio = volume_24h / liquidity if liquidity > 0 else 0
    mcap_liq_ratio = mcap / liquidity if liquidity > 0 else 0
    circ_ratio = (mcap / fdv * 100) if fdv > 0 else 0

    # Transaction analysis
    total_txns_24h = buys_24h + sells_24h
    total_txns_1h = buys_1h + sells_1h
    total_txns_6h = buys_6h + sells_6h
    buy_ratio_24h = (buys_24h / total_txns_24h * 100) if total_txns_24h > 0 else 50
    buy_ratio_1h = (buys_1h / total_txns_1h * 100) if total_txns_1h > 0 else 50
    buy_ratio_6h = (buys_6h / total_txns_6h * 100) if total_txns_6h > 0 else 50

    # Smart Money Detection
    smart_money = "NEUTRAL"
    smart_emoji = "⚖️"
    if buy_ratio_1h > buy_ratio_24h + 10 and buys_1h > 15:
        smart_money = "ACCUMULATION"
        smart_emoji = "🟢"
    elif buy_ratio_1h < buy_ratio_24h - 10 and sells_1h > 15:
        smart_money = "DISTRIBUTION"
        smart_emoji = "🔴"
    elif buy_ratio_1h > 60 and buy_ratio_6h > 55:
        smart_money = "STRONG ACCUMULATION"
        smart_emoji = "🟢"
    elif buy_ratio_1h < 40 and buy_ratio_6h < 45:
        smart_money = "HEAVY DISTRIBUTION"
        smart_emoji = "🔴"

    # Momentum Score (0-100)
    momentum_score = 50
    if change_5m > 0: momentum_score += 5
    if change_1h > 0: momentum_score += 10
    if change_6h > 0: momentum_score += 10
    if change_24h > 0: momentum_score += 10
    if buy_ratio_1h > 55: momentum_score += 5
    if buy_ratio_24h > 55: momentum_score += 5
    if volume_1h > volume_24h / 12: momentum_score += 5  # Above average hourly volume
    momentum_score = max(0, min(100, momentum_score))

    if momentum_score >= 80:
        momentum_label = "VERY BULLISH"
        momentum_emoji = "🚀"
    elif momentum_score >= 65:
        momentum_label = "BULLISH"
        momentum_emoji = "📈"
    elif momentum_score >= 45:
        momentum_label = "NEUTRAL"
        momentum_emoji = "⚖️"
    elif momentum_score >= 30:
        momentum_label = "BEARISH"
        momentum_emoji = "📉"
    else:
        momentum_label = "VERY BEARISH"
        momentum_emoji = "💥"

    # Slippage Estimation
    def estimate_slippage(trade_size, liq):
        if liq <= 0:
            return "N/A"
        impact = (trade_size / (liq * 2)) * 100
        if impact < 0.5:
            return f"~{impact:.2f}% (Low)"
        elif impact < 2:
            return f"~{impact:.1f}% (Moderate)"
        elif impact < 5:
            return f"~{impact:.1f}% (High)"
        else:
            return f"~{impact:.0f}% (EXTREME)"

    slip_1k = estimate_slippage(1000, liquidity)
    slip_5k = estimate_slippage(5000, liquidity)
    slip_10k = estimate_slippage(10000, liquidity)

    # Entry/Exit Zones (based on price action)
    price_float = float(price) if price != "0" else 0
    if price_float > 0:
        # Support zone: lowest implied price from recent changes
        support_price = price_float / (1 + max(change_1h, change_6h, change_24h) / 100) if max(change_1h, change_6h, change_24h) > 0 else price_float * 0.9
        resistance_price = price_float * (1 + abs(min(change_1h, change_6h, change_24h)) / 100) if min(change_1h, change_6h, change_24h) < 0 else price_float * 1.15
        stop_loss = price_float * 0.85  # 15% below current
        tp1 = price_float * 1.25  # 25% above
        tp2 = price_float * 1.50  # 50% above
        tp3 = price_float * 2.00  # 100% above (2x)
    else:
        support_price = resistance_price = stop_loss = tp1 = tp2 = tp3 = 0

    def fmt_price(p):
        if p == 0: return "N/A"
        if p < 0.00001: return f"${p:,.10f}"
        if p < 0.001: return f"${p:,.8f}"
        if p < 1: return f"${p:,.6f}"
        if p < 100: return f"${p:,.4f}"
        return f"${p:,.2f}"

    # ==================== SCORING ====================
    score = 5.0

    # Liquidity scoring
    if liquidity >= 500000:
        score += 2.0; liq_grade = "Excellent"; liq_emoji = "🟢"
    elif liquidity >= 100000:
        score += 1.5; liq_grade = "Strong"; liq_emoji = "🟢"
    elif liquidity >= 30000:
        score += 0.5; liq_grade = "Moderate"; liq_emoji = "🟡"
    elif liquidity >= 5000:
        score -= 0.5; liq_grade = "Low"; liq_emoji = "🟠"
    else:
        score -= 2; liq_grade = "Critical"; liq_emoji = "🔴"

    # MCap/Liq ratio scoring
    if mcap_liq_ratio < 5:
        mlr_grade = "Healthy"
        mlr_detail = "Strong liquidity backing relative to market cap. Low manipulation risk."
    elif mcap_liq_ratio < 10:
        mlr_grade = "Acceptable"
        mlr_detail = "Reasonable liquidity depth. Standard for mid-cap memecoins."
    elif mcap_liq_ratio < 20:
        mlr_grade = "Stretched"
        mlr_detail = "Market cap is significantly higher than liquidity. Price is fragile."
        score -= 0.5
    else:
        mlr_grade = "Dangerous"
        mlr_detail = "Extremely thin liquidity relative to market cap. Price can crash with minimal selling."
        score -= 1.5

    # Volume analysis
    if vol_liq_ratio > 5:
        vol_assessment = "Extremely high volume relative to liquidity — possible wash trading or peak hype phase."
    elif vol_liq_ratio > 2:
        vol_assessment = "High trading activity — strong interest but watch for volatility spikes."
    elif vol_liq_ratio > 0.5:
        vol_assessment = "Healthy volume-to-liquidity ratio — organic trading activity."
    elif vol_liq_ratio > 0.1:
        vol_assessment = "Low trading activity — limited market interest at current levels."
    else:
        vol_assessment = "Minimal volume — token may be abandoned or in very early stage."

    # Volume trend
    avg_hourly = volume_24h / 24 if volume_24h > 0 else 0
    if volume_1h > avg_hourly * 2:
        vol_trend = "📈 ACCELERATING — Current hour volume is 2x+ above 24h average"
        score += 0.5
    elif volume_1h > avg_hourly * 1.2:
        vol_trend = "↗️ INCREASING — Above average trading activity"
    elif volume_1h > avg_hourly * 0.5:
        vol_trend = "➡️ STABLE — Normal trading activity"
    else:
        vol_trend = "📉 DECLINING — Below average, interest may be fading"
        score -= 0.5

    # Security scoring
    sec_issues = []
    if risk_level == "GOOD":
        score += 1.5; sec_grade = "Safe"; sec_emoji = "🟢"
    elif risk_level == "WARN":
        score += 0; sec_grade = "Caution"; sec_emoji = "🟡"
    elif risk_level == "BAD":
        score -= 1.5; sec_grade = "Risky"; sec_emoji = "🟠"
    elif risk_level == "DANGER":
        score -= 3; sec_grade = "Dangerous"; sec_emoji = "🔴"
    else:
        sec_grade = "Unknown"; sec_emoji = "⚪"

    if mint_auth:
        score -= 1
        sec_issues.append("🚩 MINT AUTHORITY ENABLED — Developers can create unlimited new tokens, diluting your holdings to zero.")
    if freeze_auth:
        score -= 0.5
        sec_issues.append("🚩 FREEZE AUTHORITY ENABLED — Your tokens can be frozen, preventing you from selling.")
    if is_mutable:
        sec_issues.append("🚩 MUTABLE METADATA — Token info (name, symbol, image) can be changed without notice.")
    if insider_pct > 30:
        score -= 2
        sec_issues.append(f"🚩 HIGH INSIDER CONCENTRATION ({insider_pct:.1f}%) — Insiders control a massive portion. Coordinated dump risk is extreme.")
    elif insider_pct > 15:
        score -= 1
        sec_issues.append(f"⚠️ NOTABLE INSIDER HOLDINGS ({insider_pct:.1f}%) — Monitor for potential insider selling.")

    # Price action
    if change_24h > 100:
        price_status = "Parabolic Pump"; price_emoji = "🚀"
        price_detail = "Extreme upward movement — historically followed by 50-80% corrections. Very high risk entry."
    elif change_24h > 50:
        price_status = "Strong Rally"; price_emoji = "📈"
        price_detail = "Significant momentum. Consider waiting for a 20-30% pullback before entering."
    elif change_24h > 10:
        price_status = "Uptrend"; price_emoji = "📈"
        price_detail = "Positive momentum with healthy gains. Trend appears sustainable if volume supports."
    elif change_24h > 0:
        price_status = "Slight Uptrend"; price_emoji = "↗️"
        price_detail = "Minor positive movement. Market is relatively stable — good for accumulation."
    elif change_24h > -10:
        price_status = "Slight Downtrend"; price_emoji = "↘️"
        price_detail = "Minor correction. Could be normal market fluctuation or early distribution."
    elif change_24h > -30:
        price_status = "Downtrend"; price_emoji = "📉"
        price_detail = "Notable selling pressure. Watch for support levels and reversal signals."
    elif change_24h > -50:
        price_status = "Heavy Selling"; price_emoji = "📉"
        price_detail = "Significant dump in progress. Do NOT catch falling knives."
    else:
        price_status = "Crash"; price_emoji = "💥"
        price_detail = "Severe price collapse. Possible rug pull or major negative event."

    # Holder analysis
    if top10_pct > 80:
        holder_grade = "Extremely Concentrated"; holder_emoji = "🔴"
        holder_detail = "Top 10 wallets control 80%+ of supply. Single wallet can crash the entire token."
        whale_dump_risk = "VERY HIGH"
    elif top10_pct > 50:
        holder_grade = "Highly Concentrated"; holder_emoji = "🟠"
        holder_detail = "Top 10 hold majority. Coordinated selling would devastate the price."
        whale_dump_risk = "HIGH"
    elif top10_pct > 30:
        holder_grade = "Moderately Concentrated"; holder_emoji = "🟡"
        holder_detail = "Moderate concentration. Some whale risk but manageable with stop-losses."
        whale_dump_risk = "MODERATE"
    else:
        holder_grade = "Well Distributed"; holder_emoji = "🟢"
        holder_detail = "Healthy distribution. Lower risk of coordinated dumps."
        whale_dump_risk = "LOW"

    # Risk-Reward calculation
    potential_upside = 50 if score >= 7 else 30 if score >= 5 else 15
    potential_downside = 15 if score >= 7 else 30 if score >= 5 else 60
    rr_ratio = potential_upside / potential_downside if potential_downside > 0 else 0

    if rr_ratio >= 2:
        rr_grade = "FAVORABLE"
        rr_emoji = "🟢"
    elif rr_ratio >= 1:
        rr_grade = "BALANCED"
        rr_emoji = "🟡"
    else:
        rr_grade = "UNFAVORABLE"
        rr_emoji = "🔴"

    # Position sizing recommendation
    if score >= 8:
        position_rec = "Up to 3-5% of portfolio. Strong fundamentals support a meaningful position."
    elif score >= 6:
        position_rec = "1-2% of portfolio. Decent setup but manage risk with stop-losses."
    elif score >= 4:
        position_rec = "0.5-1% of portfolio MAX. High risk — only risk what you can afford to lose."
    else:
        position_rec = "AVOID or 0.1% max. Risk factors are too significant for meaningful allocation."

    # Score clamping
    score = max(1, min(10, round(score, 1)))

    # Final verdict
    if score >= 8:
        verdict = "STRONG BUY"; verdict_emoji = "🟢"
        verdict_detail = "Strong fundamentals across all metrics. Relatively low risk for the category."
    elif score >= 6:
        verdict = "CAUTIOUS BUY"; verdict_emoji = "🟢"
        verdict_detail = "Decent fundamentals with manageable risks. Use stop-losses and proper position sizing."
    elif score >= 5:
        verdict = "NEUTRAL"; verdict_emoji = "🟡"
        verdict_detail = "Mixed signals. Wait for clearer direction before committing capital."
    elif score >= 3:
        verdict = "CAUTIOUS"; verdict_emoji = "🟠"
        verdict_detail = "Multiple risk factors detected. Only consider with very small position size."
    else:
        verdict = "HIGH RISK"; verdict_emoji = "🔴"
        verdict_detail = "Significant red flags. Avoid or exit existing positions immediately."

    # ==================== BUILD PREMIUM REPORT ====================

    short_addr = f"{address[:6]}...{address[-4:]}" if len(address) > 10 else address

    report = f"""🔎 SOLANA TOKEN INTELLIGENCE REPORT

📌 {name} (${symbol})
📋 Contract: {short_addr}
💰 Price: ${price}
📅 Age: {age} | DEX: {dex} | Pairs: {total_pairs}


1. EXECUTIVE SUMMARY

{verdict_emoji} Score: {score}/10 — {verdict}
{verdict_detail}
{momentum_emoji} Momentum: {momentum_label} ({momentum_score}/100)
{smart_emoji} Smart Money: {smart_money}


2. MARKET POSITION

💎 Market Cap: ${mcap:,.0f}
🔮 FDV: ${fdv:,.0f}
📊 Circulation: {circ_ratio:.1f}% of total supply in circulation
{'📋 ' + str(round(circ_ratio, 1)) + '% circulation means ' + ('healthy token distribution.' if circ_ratio > 50 else 'significant locked/unvested supply — watch for future unlocks.') if fdv > 0 else ''}


3. LIQUIDITY HEALTH

{liq_emoji} Liquidity: ${liquidity:,.0f} — {liq_grade}
📐 MCap/Liq Ratio: {mcap_liq_ratio:.1f}x — {mlr_grade}
{mlr_detail}

💱 Estimated Slippage:
  $1,000 trade: {slip_1k}
  $5,000 trade: {slip_5k}
  $10,000 trade: {slip_10k}


4. VOLUME & MOMENTUM

📊 24h Volume: ${volume_24h:,.0f}
⚡ 6h Volume: ${volume_6h:,.0f}
🔥 1h Volume: ${volume_1h:,.0f}
🔄 Vol/Liq Ratio: {vol_liq_ratio:.2f}x

{vol_assessment}

📈 Volume Trend: {vol_trend}
{momentum_emoji} Momentum Score: {momentum_score}/100 — {momentum_label}


5. PRICE ACTION & ENTRY ZONES

{price_emoji} Status: {price_status}
{price_detail}

⏱ 5 min: {'+' if change_5m >= 0 else ''}{change_5m}%
🕐 1 hour: {'+' if change_1h >= 0 else ''}{change_1h}%
🕕 6 hours: {'+' if change_6h >= 0 else ''}{change_6h}%
📆 24 hours: {'+' if change_24h >= 0 else ''}{change_24h}%

🎯 Entry Zones & Targets:
  🟢 Support Zone: {fmt_price(support_price)}
  🔴 Resistance: {fmt_price(resistance_price)}
  🛑 Stop Loss: {fmt_price(stop_loss)} (-15%)
  🎯 TP1: {fmt_price(tp1)} (+25%)
  🎯 TP2: {fmt_price(tp2)} (+50%)
  🚀 TP3: {fmt_price(tp3)} (+100%)


6. SMART MONEY ANALYSIS

{smart_emoji} Signal: {smart_money}

📊 Buy/Sell Ratio Across Timeframes:
  24h: {buy_ratio_24h:.1f}% buy ({buys_24h:,} buys / {sells_24h:,} sells)
  6h:  {buy_ratio_6h:.1f}% buy ({buys_6h:,} buys / {sells_6h:,} sells)
  1h:  {buy_ratio_1h:.1f}% buy ({buys_1h:,} buys / {sells_1h:,} sells)"""

    # Smart money interpretation
    if smart_money == "ACCUMULATION" or smart_money == "STRONG ACCUMULATION":
        report += "\n\n🟢 Recent buying pressure is increasing relative to historical average — potential smart money accumulation."
    elif smart_money == "DISTRIBUTION" or smart_money == "HEAVY DISTRIBUTION":
        report += "\n\n🔴 Recent selling pressure is increasing — possible smart money distribution. Exercise caution."
    else:
        report += "\n\n⚖️ Balanced flow across timeframes — no clear smart money signal detected."

    report += f"""


7. SECURITY AUDIT

{sec_emoji} Risk Level: {sec_grade} (RugCheck Score: {risk_score or 'N/A'})

🔑 Mint Authority: {'⚠️ ENABLED — CRITICAL RISK' if mint_auth else '✅ Disabled — Safe'}
❄️ Freeze Authority: {'⚠️ ENABLED — HIGH RISK' if freeze_auth else '✅ Disabled — Safe'}
📝 Mutable Metadata: {'⚠️ YES — Moderate Risk' if is_mutable else '✅ No — Safe'}
👥 Insider Holdings: {insider_pct:.1f}%"""

    if sec_issues:
        report += "\n\n⚠️ Security Concerns:"
        for issue in sec_issues:
            report += f"\n  {issue}"

    if risks:
        report += "\n\n🔍 Detected Vulnerabilities:"
        for r in risks[:8]:
            level_icon = "🔴" if r.get("level") == "danger" else "🟠" if r.get("level") == "warn" else "🟡"
            report += f"\n  {level_icon} {r.get('name', 'N/A')}: {r.get('description', '')[:120]}"

    report += f"""


8. WHALE & HOLDER INTELLIGENCE

{holder_emoji} Distribution: {holder_grade}
{holder_detail}

📊 Top 10 Holders: {top10_pct:.1f}% of supply
👥 Insider Ratio: {insider_pct:.1f}%
🐋 Whale Dump Risk: {whale_dump_risk}"""

    holders = rug_data.get("top_holders", [])
    if holders:
        report += "\n\n🏦 Top Holders:"
        for i, h in enumerate(holders[:7], 1):
            addr = h.get('address', 'N/A')
            short = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 10 else addr
            insider_tag = " 🐋 INSIDER" if h.get("insider") else ""
            pct = h.get('pct', 0)
            bar_len = min(int(pct / 2), 20)
            bar = "█" * bar_len
            report += f"\n  #{i} {short} {bar} {pct}%{insider_tag}"

    report += f"""


9. RISK-REWARD MATRIX

{rr_emoji} Risk-Reward: {rr_grade} ({rr_ratio:.1f}:1)
📈 Potential Upside: +{potential_upside}%
📉 Potential Downside: -{potential_downside}%
💼 Position Sizing: {position_rec}


10. FINAL VERDICT

{verdict_emoji} Score: {score}/10 — {verdict}

{verdict_detail}

Powered by kodarkweb3 | For help & collaboration @yms56"""

    return report
