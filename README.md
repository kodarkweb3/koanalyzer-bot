# KoAnalyzer Bot

**Solana Based Coins Analyzer Tool** - A professional Telegram bot for Solana token intelligence.

## Features

- **Whale Watch** - Track large wallet movements and detect whale activity
- **Risk Assessment** - Scan tokens for rug pull risks, mint/freeze authority and security threats
- **Holder Analysis** - Analyze top holder distribution, insider percentage and token concentration
- **Market Signals** - Live Fear & Greed Index, BTC Dominance and SOL price tracking
- **Token Analysis** - Deep dive into any Solana token with liquidity, volume and price data
- **AI-Powered Reports** - Comprehensive analysis powered by OpenAI (optional)
- **Telegram Stars Payment** - Built-in premium subscription system

## APIs Used

| API | Purpose |
|-----|---------|
| [DexScreener](https://dexscreener.com) | Token price, liquidity, volume, transactions |
| [RugCheck](https://rugcheck.xyz) | Security analysis, holder data, risk scoring |
| [CoinGecko](https://coingecko.com) | BTC dominance, SOL price, market cap |
| [Alternative.me](https://alternative.me) | Crypto Fear & Greed Index |
| [OpenAI](https://openai.com) | AI-powered token analysis (optional) |

## Setup

See [DEPLOY_GUIDE.md](DEPLOY_GUIDE.md) for detailed deployment instructions.

### Quick Start

1. Clone this repository
2. Set environment variables:
   - `TELEGRAM_BOT_TOKEN` - Your Telegram bot token
   - `OPENAI_API_KEY` - (Optional) OpenAI API key
3. Install dependencies: `pip install -r requirements.txt`
4. Run: `python3 bot.py`

### Docker

```bash
docker build -t koanalyzer-bot .
docker run -e TELEGRAM_BOT_TOKEN=your_token koanalyzer-bot
```

## Project Structure

```
koanalyzer-bot/
├── bot.py              # Main bot application
├── api_client.py       # API integrations
├── ai_analyzer.py      # Token analysis engine
├── requirements.txt    # Python dependencies
├── Dockerfile          # Docker configuration
├── Procfile            # Railway/Render process file
├── railway.toml        # Railway configuration
└── .gitignore          # Git ignore rules
```

## License

This project is proprietary. All rights reserved.

## Contact

- **Founder:** [@kodarkweb3](https://x.com/kodarkweb3)
- **Bot:** [@KoAnalyzerBot](https://t.me/KoAnalyzerBot)
