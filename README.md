# 🎴 Pokemon Card Sniper Bot (Australia)

Telegram bot that monitors Australian retailers for Pokemon TCG restocks at MSRP.

## Features

- 🏪 **8 AU Retailers**: EB Games, JB Hi-Fi, Big W, Target, Pokemon Center AU, Gameology, Good Games, Zing
- 💰 **MSRP Filtering**: Only alerts when price is at or below MSRP (5% tolerance)
- 🔄 **Shopify API + HTML Scraping**: Uses JSON API for Shopify stores, HTML patterns for others
- 🚨 **Anti-Spam**: Alerts once per restock, resets when item goes OOS
- ⚡ **Fast Polling**: Checks every 10-30 seconds (configurable)

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/add <url> <name>` | Track a product (auto-detects retailer & MSRP) |
| `/addmsrp <url> <price> <name>` | Track with custom MSRP |
| `/remove <url>` | Stop tracking |
| `/list` | Show all tracked products |
| `/retailers` | List supported AU retailers |
| `/msrp` | Show known MSRP prices in AUD |
| `/status` | Bot statistics |

## Known MSRP (AUD)

| Product | MSRP |
|---------|------|
| Booster Pack | $6.95 |
| Booster Bundle | $34.95 |
| Elite Trainer Box | $79.95 |
| Booster Box | $215.00 |
| Ultra Premium Collection | $179.95 |
| Tin | $34.95 |

## Deploy to Railway

### 1. Create Telegram Bot
1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow prompts
3. Copy the bot token

### 2. Get Your Chat ID
1. Message [@userinfobot](https://t.me/userinfobot) on Telegram
2. Copy your chat ID number

### 3. Deploy on Railway
1. Push code to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Add environment variables:
   - `TELEGRAM_BOT_TOKEN` = your bot token
   - `CHAT_ID` = your chat ID
   - `CHECK_INTERVAL` = `15` (seconds between checks)
4. Railway auto-detects the Procfile and deploys

### 4. Start Tracking
Message your bot:
```
/add https://www.ebgames.com.au/product/12345 Pokemon SV8 Surging Sparks ETB
/add https://www.gameology.com.au/products/pokemon-etb Pokemon SV8 ETB
/addmsrp https://www.bigw.com.au/product/pokemon-booster-box 215.00 Pokemon SV8 Booster Box
```

## Local Development

```bash
cp .env.example .env
# Edit .env with your tokens
pip install -r requirements.txt
uvicorn main:app --reload
```
