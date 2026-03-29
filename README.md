# kodark.io Bot v4.0

**Solana Memecoins Analyzer** - A professional Telegram bot for Solana token intelligence.

## Features

- **Free Tier** - 3 free analyses + 3 free price alarms for new users
- **Premium** - ~$7.99/month via Telegram Stars for unlimited access
- **Whale Watch** - Track large wallet movements and detect whale activity (Premium)
- **Risk Assessment** - Scan tokens for rug pull risks, mint/freeze authority and security threats
- **Holder Analysis** - Analyze top holder distribution, insider percentage and token concentration
- **Price Alarms** - Set custom price targets and get notified when conditions are met
- **Auto-Sniper Alerts** - New token launch alerts on Pump.fun, Raydium, Jupiter (Premium)
- **Advanced Charts** - Professional 24h price/volume charts inside Telegram (Premium)
- **Market Signals** - Live Fear & Greed Index, BTC Dominance and SOL price tracking (Premium)
- **AI-Powered Reports** - Comprehensive analysis powered by OpenAI
- **Multi-Language** - Full support for 15 languages
- **Feedback System** - Users can send feedback directly to the team
- **Admin Panel** - User stats, analytics, feedback viewer, broadcast messaging

## APIs Used

| API | Purpose |
|-----|---------|
| [DexScreener](https://dexscreener.com) | Token price, liquidity, volume, transactions |
| [RugCheck](https://rugcheck.xyz) | Security analysis, holder data, risk scoring |
| [CoinGecko](https://coingecko.com) | BTC dominance, SOL price, market cap |
| [Alternative.me](https://alternative.me) | Crypto Fear & Greed Index |
| [OpenAI](https://openai.com) | AI-powered token analysis |

## Setup

See [DEPLOY_GUIDE.md](DEPLOY_GUIDE.md) for detailed deployment instructions.

### Quick Start

1. Clone this repository
2. Set environment variables:
   - `TELEGRAM_BOT_TOKEN` - Your Telegram bot token
   - `ADMIN_USER_ID` - Your Telegram user ID
   - `OPENAI_API_KEY` - OpenAI API key
   - `DATA_DIR` - (Optional) Path for persistent data storage
3. Install dependencies: `pip install -r requirements.txt`
4. Run: `python3 bot.py`

### Docker

```bash
docker build -t kodark-bot .
docker run -e TELEGRAM_BOT_TOKEN=your_token -e ADMIN_USER_ID=your_id -e OPENAI_API_KEY=your_key kodark-bot
```

## Project Structure

```
kodark-bot/
├── bot.py              # Main bot application
├── api_client.py       # API integrations
├── ai_analyzer.py      # AI-powered token analysis engine
├── alarm_manager.py    # Price alarm system
├── whale_monitor.py    # Whale tracking & alerts
├── sniper_alerts.py    # Auto-sniper new token detection
├── chart_generator.py  # Price chart generation
├── languages.py        # Multi-language support (15 languages)
├── requirements.txt    # Python dependencies
├── Dockerfile          # Docker configuration
├── Procfile            # Railway/Render process file
├── railway.toml        # Railway configuration
└── .gitignore          # Git ignore rules
```

## License

This project is proprietary. All rights reserved.

## Contact

- **Developer:** [@kodarkweb3](https://x.com/kodarkweb3)
- **Bot:** [@KoAnalyzerBot](https://t.me/KoAnalyzerBot)
- **X:** [@kodarkio](https://x.com/kodarkio)
