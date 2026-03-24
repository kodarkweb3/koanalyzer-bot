"""
Solana DexScreener & RugCheck API Client
API integration for token data, market info and security analysis.
"""

import requests
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ==================== DEXSCREENER API ====================

def get_token_info(token_address: str) -> dict:
    """Fetch token information from DexScreener API."""
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()

        if not data.get("pairs") or len(data["pairs"]) == 0:
            return {"error": "Token not found or no listed pairs available."}

        # Select pair with highest liquidity
        pairs = data["pairs"]
        best_pair = max(pairs, key=lambda x: float(x.get("liquidity", {}).get("usd", 0) or 0))

        token_data = {
            "name": best_pair.get("baseToken", {}).get("name", "Unknown"),
            "symbol": best_pair.get("baseToken", {}).get("symbol", "???"),
            "address": token_address,
            "price_usd": best_pair.get("priceUsd", "0"),
            "price_native": best_pair.get("priceNative", "0"),
            "market_cap": best_pair.get("marketCap", 0) or best_pair.get("fdv", 0),
            "fdv": best_pair.get("fdv", 0),
            "liquidity_usd": best_pair.get("liquidity", {}).get("usd", 0),
            "volume_24h": best_pair.get("volume", {}).get("h24", 0),
            "volume_6h": best_pair.get("volume", {}).get("h6", 0),
            "volume_1h": best_pair.get("volume", {}).get("h1", 0),
            "price_change_5m": best_pair.get("priceChange", {}).get("m5", 0),
            "price_change_1h": best_pair.get("priceChange", {}).get("h1", 0),
            "price_change_6h": best_pair.get("priceChange", {}).get("h6", 0),
            "price_change_24h": best_pair.get("priceChange", {}).get("h24", 0),
            "txns_buy_24h": best_pair.get("txns", {}).get("h24", {}).get("buys", 0),
            "txns_sell_24h": best_pair.get("txns", {}).get("h24", {}).get("sells", 0),
            "txns_buy_1h": best_pair.get("txns", {}).get("h1", {}).get("buys", 0),
            "txns_sell_1h": best_pair.get("txns", {}).get("h1", {}).get("sells", 0),
            "txns_buy_6h": best_pair.get("txns", {}).get("h6", {}).get("buys", 0),
            "txns_sell_6h": best_pair.get("txns", {}).get("h6", {}).get("sells", 0),
            "pair_address": best_pair.get("pairAddress", ""),
            "dex_id": best_pair.get("dexId", ""),
            "pair_created_at": best_pair.get("pairCreatedAt", None),
            "url": best_pair.get("url", ""),
            "total_pairs": len(pairs),
        }

        # Calculate pair age
        if token_data["pair_created_at"]:
            try:
                created = datetime.fromtimestamp(token_data["pair_created_at"] / 1000)
                age = datetime.now() - created
                if age.days > 0:
                    token_data["age"] = f"{age.days} days"
                elif age.seconds > 3600:
                    token_data["age"] = f"{age.seconds // 3600} hours"
                else:
                    token_data["age"] = f"{age.seconds // 60} minutes"
            except:
                token_data["age"] = "Unknown"
        else:
            token_data["age"] = "Unknown"

        return token_data

    except requests.exceptions.Timeout:
        return {"error": "DexScreener API timed out. Please try again."}
    except requests.exceptions.RequestException as e:
        logger.error(f"DexScreener API error: {e}")
        return {"error": f"Could not reach DexScreener API: {str(e)}"}
    except Exception as e:
        logger.error(f"Error fetching token info: {e}")
        return {"error": f"Unexpected error: {str(e)}"}


# ==================== RUGCHECK API ====================

def get_rugcheck_info(token_address: str) -> dict:
    """Fetch token security information from RugCheck API."""
    try:
        url = f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()

        risk_score = data.get("score", None)
        risks = data.get("risks", [])

        # Determine risk level
        if risk_score is not None:
            if risk_score >= 800:
                risk_level = "GOOD"
                risk_emoji = "🟢"
            elif risk_score >= 500:
                risk_level = "WARN"
                risk_emoji = "🟡"
            elif risk_score >= 200:
                risk_level = "BAD"
                risk_emoji = "🟠"
            else:
                risk_level = "DANGER"
                risk_emoji = "🔴"
        else:
            risk_level = "UNKNOWN"
            risk_emoji = "⚪"

        # Top holder info
        top_holders = data.get("topHolders", [])
        holder_info = []
        total_top10_pct = 0
        for h in top_holders[:10]:
            pct = round(h.get("pct", 0), 2)
            total_top10_pct += pct
            holder_info.append({
                "address": h.get("address", ""),
                "pct": pct,
                "insider": h.get("insider", False),
            })

        # Total insider percentage
        total_insider_pct = sum(h.get("pct", 0) for h in top_holders if h.get("insider", False))

        rug_data = {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_emoji": risk_emoji,
            "risks": [{"name": r.get("name", ""), "description": r.get("description", ""), "level": r.get("level", "")} for r in risks],
            "top_holders": holder_info,
            "total_top10_pct": round(total_top10_pct, 2),
            "total_insider_pct": round(total_insider_pct, 2),
            "mint_authority": data.get("mintAuthority", None),
            "freeze_authority": data.get("freezeAuthority", None),
            "is_mutable": data.get("tokenMeta", {}).get("mutable", None),
            "total_holders_count": len(top_holders),
        }

        return rug_data

    except requests.exceptions.Timeout:
        return {"error": "RugCheck API timed out."}
    except requests.exceptions.RequestException as e:
        logger.error(f"RugCheck API error: {e}")
        return {"error": f"Could not reach RugCheck API: {str(e)}"}
    except Exception as e:
        logger.error(f"Error fetching RugCheck info: {e}")
        return {"error": f"Unexpected error: {str(e)}"}


# ==================== MARKET DATA ====================

def get_fear_greed_index() -> dict:
    """Fetch Crypto Fear & Greed Index data."""
    try:
        url = "https://api.alternative.me/fng/?limit=1"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("data"):
            fng = data["data"][0]
            value = int(fng.get("value", 0))
            classification = fng.get("value_classification", "Unknown")

            if value <= 25:
                emoji = "😱"
            elif value <= 45:
                emoji = "😰"
            elif value <= 55:
                emoji = "😐"
            elif value <= 75:
                emoji = "😊"
            else:
                emoji = "🤑"

            return {
                "value": value,
                "classification": classification,
                "emoji": emoji,
            }
        return {"error": "Data unavailable."}
    except Exception as e:
        logger.error(f"Fear & Greed error: {e}")
        return {"error": str(e)}


def get_btc_dominance() -> dict:
    """Fetch BTC Dominance data."""
    try:
        url = "https://api.coingecko.com/api/v3/global"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        global_data = data.get("data", {})
        btc_dom = global_data.get("market_cap_percentage", {}).get("btc", 0)
        total_mcap = global_data.get("total_market_cap", {}).get("usd", 0)
        total_volume = global_data.get("total_volume", {}).get("usd", 0)
        mcap_change = global_data.get("market_cap_change_percentage_24h_usd", 0)

        return {
            "btc_dominance": round(btc_dom, 2),
            "total_market_cap": total_mcap,
            "total_volume_24h": total_volume,
            "market_cap_change_24h": round(mcap_change, 2),
        }
    except Exception as e:
        logger.error(f"BTC Dominance error: {e}")
        return {"error": str(e)}


def get_solana_price() -> dict:
    """Fetch Solana price information."""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd&include_24hr_change=true&include_market_cap=true"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        sol = data.get("solana", {})
        return {
            "price": sol.get("usd", 0),
            "change_24h": round(sol.get("usd_24h_change", 0), 2),
            "market_cap": sol.get("usd_market_cap", 0),
        }
    except Exception as e:
        logger.error(f"Solana price error: {e}")
        return {"error": str(e)}


# ==================== TRENDING TOKENS ====================

def get_trending_solana_tokens() -> list:
    """Fetch trending Solana tokens from DexScreener."""
    try:
        url = "https://api.dexscreener.com/token-boosts/top/v1"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()

        solana_tokens = []
        for token in data:
            if token.get("chainId") == "solana":
                solana_tokens.append({
                    "address": token.get("tokenAddress", ""),
                    "description": token.get("description", ""),
                    "url": token.get("url", ""),
                    "icon": token.get("icon", ""),
                })
            if len(solana_tokens) >= 5:
                break

        return solana_tokens
    except Exception as e:
        logger.error(f"Trending tokens error: {e}")
        return []
