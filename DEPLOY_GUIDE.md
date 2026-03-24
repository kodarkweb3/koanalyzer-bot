# KoAnalyzer Bot - Deployment Guide

## Prerequisites

- GitHub account
- Railway.app account (free tier available)
- Telegram Bot Token (from @BotFather)

## Step 1: Create a GitHub Repository

1. Go to [github.com/new](https://github.com/new)
2. Repository name: `koanalyzer-bot`
3. Choose your preferred visibility (Public or Private)
4. Click **Create repository**

## Step 2: Upload Project Files

1. On your repo page, click **"uploading an existing file"**
2. Upload the following files:
   - `bot.py`
   - `api_client.py`
   - `ai_analyzer.py`
   - `requirements.txt`
   - `Dockerfile`
   - `Procfile`
   - `railway.toml`
   - `.gitignore`
3. Click **Commit changes**

**IMPORTANT:** Do NOT upload `.env`, `user_data.json`, or `bot.log` files. These contain sensitive data and are excluded by `.gitignore`.

## Step 3: Deploy on Railway

1. Go to [railway.app](https://railway.app)
2. Log in with your GitHub account
3. Click **+ New** then select **GitHub Repository**
4. Select your `koanalyzer-bot` repository
5. Railway will automatically detect the Dockerfile and start building

## Step 4: Add Environment Variables

In Railway, click on your service, go to the **Variables** tab, and add:

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token from @BotFather |
| `ADMIN_USER_ID` | Your Telegram user ID (for owner/admin privileges) |
| `PROMO_CODE` | (Optional) Promo code command name for free trials |
| `OPENAI_API_KEY` | (Optional) OpenAI API key for AI-powered analysis |

Click **Deploy** to apply the changes.

## Step 5: Verify

1. Check the **Deployments** tab for successful build
2. Look for `Bot started successfully! Polling...` in the logs
3. Open Telegram and send `/start` to your bot

## Updating the Bot

1. Go to your GitHub repository
2. Click on the file to update, then click the pencil icon to edit
3. Or use **Add file** > **Upload files** to upload new versions
4. Commit the changes
5. Railway will automatically detect changes and redeploy

## Troubleshooting

- **Bot not responding:** Check Railway Deployments > Logs for errors
- **Conflict error:** Make sure the bot is only running in one place (Railway only)
- **Token error:** Verify `TELEGRAM_BOT_TOKEN` in the Variables tab
- **Payment not working:** Ensure Telegram Stars payments are enabled via @BotFather

## Tech Stack

- Python 3.11
- python-telegram-bot 20.7
- DexScreener API
- RugCheck API
- CoinGecko API
- OpenAI API (optional)
