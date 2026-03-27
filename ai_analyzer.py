"""
AI-Powered Token Analysis Engine
Analyzes Solana token data and generates professional investment reports.
"""

import logging
import os
from openai import OpenAI

logger = logging.getLogger(__name__)


def analyze_token(token_data: dict, rug_data: dict) -> str:
    """
    Analyze token data and security info to generate
    a professional report.
    """
    try:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if api_key:
            return _ai_analysis(token_data, rug_data, api_key)
    except Exception as e:
        logger.warning(f"AI analysis failed, falling back to rule-based: {e}")

    return _rule_based_analysis(token_data, rug_data)


def _ai_analysis(token_data: dict, rug_data: dict, api_key: str) -> str:
    """Advanced analysis using OpenAI API."""
    try:
        client = OpenAI(api_key=api_key)

        prompt = f"""You are an elite Solana blockchain analyst working for a professional crypto intelligence firm. Analyze the following token data and produce a comprehensive English investment report.

TOKEN DATA:
- Name: {token_data.get('name', 'N/A')} ({token_data.get('symbol', 'N/A')})
- Contract: {token_data.get('address', 'N/A')}
- Price: ${token_data.get('price_usd', '0')}
- Market Cap: ${token_data.get('market_cap', 0):,.0f}
- FDV: ${float(token_data.get('fdv', 0) or 0):,.0f}
- Liquidity: ${token_data.get('liquidity_usd', 0):,.0f}
- 24h Volume: ${token_data.get('volume_24h', 0):,.0f}
- 6h Volume: ${token_data.get('volume_6h', 0):,.0f}
- 1h Volume: ${token_data.get('volume_1h', 0):,.0f}
- 5m Change: {token_data.get('price_change_5m', 0)}%
- 1h Change: {token_data.get('price_change_1h', 0)}%
- 6h Change: {token_data.get('price_change_6h', 0)}%
- 24h Change: {token_data.get('price_change_24h', 0)}%
- 24h Buys: {token_data.get('txns_buy_24h', 0)} | Sells: {token_data.get('txns_sell_24h', 0)}
- 1h Buys: {token_data.get('txns_buy_1h', 0)} | Sells: {token_data.get('txns_sell_1h', 0)}
- Age: {token_data.get('age', 'Unknown')}
- DEX: {token_data.get('dex_id', 'N/A')}
- Total Pairs: {token_data.get('total_pairs', 1)}

SECURITY DATA:
- Risk Score: {rug_data.get('risk_score', 'N/A')}
- Risk Level: {rug_data.get('risk_level', 'N/A')}
- Insider Percentage: {rug_data.get('total_insider_pct', 0)}%
- Top 10 Holders: {rug_data.get('total_top10_pct', 'N/A')}%
- Mint Authority: {rug_data.get('mint_authority', 'None')}
- Freeze Authority: {rug_data.get('freeze_authority', 'None')}
- Mutable Metadata: {rug_data.get('is_mutable', 'N/A')}
- Detected Risks: {', '.join([r['name'] + ' (' + r.get('level','') + ')' for r in rug_data.get('risks', [])])}

TOP HOLDERS:
{_format_holders_for_prompt(rug_data.get('top_holders', []))}

Generate a professional report with these EXACT sections. Use emojis tastefully (not excessively). Do NOT use markdown bold (asterisks). Write in plain text.

SECTIONS:
1. GENERAL OVERVIEW - Token summary, market position, age assessment, pair count
2. LIQUIDITY & VOLUME ANALYSIS - Liquidity depth, volume trends, vol/liq ratio health
3. PRICE ACTION - Multi-timeframe analysis (5m, 1h, 6h, 24h), momentum assessment
4. SECURITY & RISK ASSESSMENT - Rug pull risk, contract authorities, metadata mutability, detected vulnerabilities
5. WHALE & HOLDER ANALYSIS - Top holder concentration, insider activity, distribution health
6. TRANSACTION FLOW - Buy/sell ratio analysis, trading activity patterns
7. FINAL VERDICT - Overall score (X/10), risk rating, actionable recommendation

Be analytical, data-driven, and professional. Explain WHY each metric matters. Give specific numbers."""

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2500,
            temperature=0.7,
        )

        return response.choices[0].message.content

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
    """Comprehensive rule-based analysis without API."""

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
    age = token_data.get("age", "Unknown")
    dex = token_data.get("dex_id", "N/A").upper()
    total_pairs = token_data.get("total_pairs", 1)

    risk_score = rug_data.get("risk_score", None)
    risk_level = rug_data.get("risk_level", "UNKNOWN")
    risk_emoji = rug_data.get("risk_emoji", "⚪")
    insider_pct = float(rug_data.get("total_insider_pct", 0) or 0)
    top10_pct = float(rug_data.get("total_top10_pct", 0) or 0)
    mint_auth = rug_data.get("mint_authority", None)
    freeze_auth = rug_data.get("freeze_authority", None)
    is_mutable = rug_data.get("is_mutable", None)
    risks = rug_data.get("risks", [])

    # ==================== SCORING ====================
    score = 5.0

    # Liquidity scoring
    if liquidity >= 500000:
        score += 2.0
        liq_grade = "Excellent"
        liq_emoji = "🟢"
        liq_detail = "Deep liquidity pool provides strong price stability and low slippage for traders."
    elif liquidity >= 100000:
        score += 1.5
        liq_grade = "Strong"
        liq_emoji = "🟢"
        liq_detail = "Healthy liquidity level supports moderate trading volumes without significant price impact."
    elif liquidity >= 30000:
        score += 0.5
        liq_grade = "Moderate"
        liq_emoji = "🟡"
        liq_detail = "Acceptable liquidity but larger trades may experience notable slippage."
    elif liquidity >= 5000:
        score -= 0.5
        liq_grade = "Low"
        liq_emoji = "🟠"
        liq_detail = "Thin liquidity pool - high slippage risk. Even small sells can crash the price."
    else:
        score -= 2
        liq_grade = "Critical"
        liq_emoji = "🔴"
        liq_detail = "Dangerously low liquidity. Extremely high risk of rug pull or price manipulation."

    # Volume analysis
    vol_liq_ratio = volume_24h / liquidity if liquidity > 0 else 0
    if vol_liq_ratio > 5:
        vol_assessment = "Extremely high volume relative to liquidity - possible wash trading or hype phase."
    elif vol_liq_ratio > 2:
        vol_assessment = "High trading activity relative to pool size - strong interest but watch for volatility."
    elif vol_liq_ratio > 0.5:
        vol_assessment = "Healthy volume-to-liquidity ratio indicating organic trading activity."
    elif vol_liq_ratio > 0.1:
        vol_assessment = "Low trading activity - limited market interest at current levels."
    else:
        vol_assessment = "Minimal trading volume - token may be abandoned or in very early stage."

    # Security scoring
    sec_issues = []
    if risk_level == "GOOD":
        score += 1.5
        sec_grade = "Safe"
        sec_emoji = "🟢"
    elif risk_level == "WARN":
        score += 0
        sec_grade = "Caution"
        sec_emoji = "🟡"
    elif risk_level == "BAD":
        score -= 1.5
        sec_grade = "Risky"
        sec_emoji = "🟠"
    elif risk_level == "DANGER":
        score -= 3
        sec_grade = "Dangerous"
        sec_emoji = "🔴"
    else:
        sec_grade = "Unknown"
        sec_emoji = "⚪"

    if mint_auth:
        score -= 1
        sec_issues.append("Mint Authority is ENABLED - developers can create unlimited new tokens, diluting your holdings.")
    if freeze_auth:
        score -= 0.5
        sec_issues.append("Freeze Authority is ENABLED - your tokens can be frozen at any time.")
    if is_mutable:
        sec_issues.append("Token metadata is mutable - project info can be changed without notice.")
    if insider_pct > 30:
        score -= 2
        sec_issues.append(f"High insider concentration ({insider_pct:.1f}%) - insiders control a large portion of supply.")
    elif insider_pct > 15:
        score -= 1
        sec_issues.append(f"Notable insider holdings ({insider_pct:.1f}%) - monitor for potential dumps.")

    # Price action assessment
    if change_24h > 100:
        price_status = "Parabolic pump"
        price_detail = "Extreme upward movement - often followed by sharp corrections. High risk entry."
        price_emoji = "🚀"
    elif change_24h > 50:
        price_status = "Strong rally"
        price_detail = "Significant upward momentum. Consider waiting for a pullback before entering."
        price_emoji = "📈"
    elif change_24h > 10:
        price_status = "Uptrend"
        price_detail = "Positive momentum with healthy gains. Trend appears sustainable."
        price_emoji = "📈"
    elif change_24h > 0:
        price_status = "Slight uptrend"
        price_detail = "Minor positive movement. Market is relatively stable."
        price_emoji = "↗️"
    elif change_24h > -10:
        price_status = "Slight downtrend"
        price_detail = "Minor negative movement. Could be normal market fluctuation."
        price_emoji = "↘️"
    elif change_24h > -30:
        price_status = "Downtrend"
        price_detail = "Notable selling pressure. Watch for support levels and reversal signals."
        price_emoji = "📉"
    elif change_24h > -50:
        price_status = "Heavy selling"
        price_detail = "Significant dump in progress. Avoid catching falling knives."
        price_emoji = "📉"
    else:
        price_status = "Crash"
        price_detail = "Severe price collapse. Possible rug pull or major negative event."
        price_emoji = "💥"

    # Transaction analysis
    total_txns_24h = buys_24h + sells_24h
    total_txns_1h = buys_1h + sells_1h
    buy_ratio_24h = (buys_24h / total_txns_24h * 100) if total_txns_24h > 0 else 50
    buy_ratio_1h = (buys_1h / total_txns_1h * 100) if total_txns_1h > 0 else 50

    if buy_ratio_24h > 60:
        txn_sentiment = "Strong accumulation phase - buyers significantly outnumber sellers."
        txn_emoji = "🟢"
    elif buy_ratio_24h > 55:
        txn_sentiment = "Mild buy pressure - slightly more buying than selling activity."
        txn_emoji = "🟢"
    elif buy_ratio_24h > 45:
        txn_sentiment = "Balanced market - roughly equal buying and selling activity."
        txn_emoji = "🟡"
    elif buy_ratio_24h > 40:
        txn_sentiment = "Mild sell pressure - slightly more selling than buying activity."
        txn_emoji = "🟠"
    else:
        txn_sentiment = "Distribution phase - sellers significantly outnumber buyers."
        txn_emoji = "🔴"

    # Holder analysis
    if top10_pct > 80:
        holder_grade = "Extremely Concentrated"
        holder_detail = "Top 10 wallets control over 80% of supply. Very high manipulation risk."
        holder_emoji = "🔴"
    elif top10_pct > 50:
        holder_grade = "Highly Concentrated"
        holder_detail = "Top 10 wallets hold majority of supply. Single wallet dumps can crash the price."
        holder_emoji = "🟠"
    elif top10_pct > 30:
        holder_grade = "Moderately Concentrated"
        holder_detail = "Moderate concentration among top holders. Some whale risk but manageable."
        holder_emoji = "🟡"
    else:
        holder_grade = "Well Distributed"
        holder_detail = "Healthy token distribution. Lower risk of coordinated dumps."
        holder_emoji = "🟢"

    # Score clamping
    score = max(1, min(10, round(score, 1)))

    # Final verdict
    if score >= 8:
        verdict = "STRONG BUY"
        verdict_emoji = "🟢"
        verdict_detail = "Token shows strong fundamentals across all metrics. Relatively low risk for the category."
    elif score >= 6:
        verdict = "CAUTIOUS BUY"
        verdict_emoji = "🟢"
        verdict_detail = "Decent fundamentals with some areas of concern. Position sizing and stop-losses recommended."
    elif score >= 5:
        verdict = "NEUTRAL"
        verdict_emoji = "🟡"
        verdict_detail = "Mixed signals across metrics. Wait for clearer direction before committing capital."
    elif score >= 3:
        verdict = "CAUTIOUS"
        verdict_emoji = "🟠"
        verdict_detail = "Multiple risk factors detected. Only consider with very small position size."
    else:
        verdict = "HIGH RISK"
        verdict_emoji = "🔴"
        verdict_detail = "Significant red flags across multiple metrics. Avoid or exit existing positions."

    # ==================== BUILD REPORT ====================

    short_addr = f"{address[:6]}...{address[-4:]}" if len(address) > 10 else address

    report = f"""🔎 SOLANA TOKEN INTELLIGENCE REPORT

📌 {name} (${symbol})
📋 Contract: {short_addr}
💰 Price: ${price}
📅 Age: {age} | DEX: {dex} | Pairs: {total_pairs}

{verdict_emoji} Score: {score}/10 - {verdict}


1. GENERAL OVERVIEW

{name} is a Solana-based token currently trading at ${price} on {dex}. The token has been active for {age} and is listed on {total_pairs} trading pair(s).

💎 Market Cap: ${mcap:,.0f}
🔮 FDV: ${fdv:,.0f}
{'📊 Market cap to FDV ratio suggests ' + (str(round(mcap/fdv*100, 1)) + '% of tokens are in circulation.' if fdv > 0 else '')}


2. LIQUIDITY & VOLUME ANALYSIS

{liq_emoji} Liquidity: ${liquidity:,.0f} - {liq_grade}
{liq_detail}

📊 24h Volume: ${volume_24h:,.0f}
⚡ 6h Volume: ${volume_6h:,.0f}
🔥 1h Volume: ${volume_1h:,.0f}
🔄 Vol/Liq Ratio: {vol_liq_ratio:.2f}x

{vol_assessment}


3. PRICE ACTION

{price_emoji} Status: {price_status}
{price_detail}

⏱ 5 min: {'+' if change_5m >= 0 else ''}{change_5m}%
🕐 1 hour: {'+' if change_1h >= 0 else ''}{change_1h}%
🕕 6 hours: {'+' if change_6h >= 0 else ''}{change_6h}%
📆 24 hours: {'+' if change_24h >= 0 else ''}{change_24h}%


4. SECURITY & RISK ASSESSMENT

{sec_emoji} Risk Level: {sec_grade} (Score: {risk_score or 'N/A'})

🔑 Mint Authority: {'⚠️ ENABLED' if mint_auth else '✅ Disabled'}
❄️ Freeze Authority: {'⚠️ ENABLED' if freeze_auth else '✅ Disabled'}
📝 Mutable Metadata: {'⚠️ YES' if is_mutable else '✅ No'}
👥 Insider Holdings: {insider_pct:.1f}%"""

    if sec_issues:
        report += "\n\n⚠️ Security Concerns:"
        for issue in sec_issues:
            report += f"\n  🚩 {issue}"

    if risks:
        report += "\n\n🔍 Detected Vulnerabilities:"
        for r in risks[:6]:
            level_icon = "🔴" if r.get("level") == "danger" else "🟠" if r.get("level") == "warn" else "🟡"
            report += f"\n  {level_icon} {r.get('name', 'N/A')}: {r.get('description', '')[:100]}"

    report += f"""


5. WHALE & HOLDER ANALYSIS

{holder_emoji} Distribution: {holder_grade}
{holder_detail}

📊 Top 10 Holders: {top10_pct:.1f}% of supply
👥 Insider Ratio: {insider_pct:.1f}%"""

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


6. TRANSACTION FLOW

{txn_emoji} 24h Sentiment: {txn_sentiment}

📊 24h Transactions:
  🛒 Buys: {buys_24h:,} | 🏷 Sells: {sells_24h:,}
  📈 Buy Ratio: {buy_ratio_24h:.1f}%

⚡ 1h Transactions:
  🛒 Buys: {buys_1h:,} | 🏷 Sells: {sells_1h:,}
  📈 Buy Ratio: {buy_ratio_1h:.1f}%


7. FINAL VERDICT

{verdict_emoji} Score: {score}/10 - {verdict}

{verdict_detail}

Powered by kodarkweb3 | For help & collaboration @yms56"""

    return report
