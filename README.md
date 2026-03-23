# 🤖 Polymarket Telegram Bot

A Telegram bot for tracking Polymarket prediction markets with hourly price updates.

## ✨ Features

- 🔍 **Search Markets** - Find markets by keyword
- 📊 **Subscribe to Updates** - Get hourly price notifications
- 💰 **Real-time Prices** - Check current market prices
- 🗄️ **Smart Caching** - Fast lookups with 3-tier database system
- 📈 **Detailed Info** - Market name, outcome, bid/ask, spread, timestamp

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.8 or higher
- Telegram account
- Telegram Bot Token (get from [@BotFather](https://t.me/BotFather))

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/polymarket-telegram-bot.git
cd polymarket-telegram-bot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
nano .env  # Edit with your Telegram token
```

### 3. Get Your Telegram Bot Token

1. Open Telegram and search for [@BotFather](https://t.me/BotFather)
2. Send `/newbot`
3. Follow the instructions to create your bot
4. Copy the token and paste it in `.env`

### 4. Run the Bot
```bash
python bot_polymarket.py
```

You should see:

INFO:main:🤖 Polymarket bot started
INFO:main:✅ Scheduler started - updates every hour

## 📱 Bot Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/start` | Welcome message and help | `/start` |
| `/search <term>` | Search for markets | `/search bitcoin` |
| `/subscribe <token_id>` | Subscribe to hourly updates | `/subscribe 297637...` |
| `/sub <token_id>` | Short alias for subscribe | `/sub 297637...` |
| `/unsubscribe <token_id>` | Unsubscribe from updates | `/unsubscribe 297637...` |
| `/unsub <token_id>` | Short alias for unsubscribe | `/unsub 297637...` |
| `/status` | View your subscriptions | `/status` |
| `/check <token_id>` | Check current price | `/check 297637...` |
| `/reset` | Delete all your subscriptions | `/reset` |
| `/test` | Manually trigger updates (debug) | `/test` |

## 🎯 Usage Example

1. Search for a market:
/search trump
2. Bot shows results with token IDs:
📅 US Presidential Election
❓ Will Trump win 2024?
• Yes: /sub 29763725280755533...
• No: /sub 15902934770940509...
3. Subscribe to updates:
/sub 29763725280755533...
4. Receive hourly updates automatically! 🎉
5. To remove all subscriptions:
/reset
/confirm_reset


## 🗄️ Database Architecture

The bot uses SQLite with 3 tables:

### `subscriptions`
- Stores user subscriptions
- Links chat_id to token_id

### `market_metadata`
- Permanent storage of market info
- Question, outcome, slug, event_title
- Populated from search_cache on subscribe

### `search_cache`
- Temporary cache cleared on each search
- Pre-fills with all tokens from search results
- Ensures "Unknown" never appears after search

## 🔧 Technical Details

### APIs Used

- **Telegram Bot API** - User interaction
- **Polymarket Gamma API** - Market search and metadata
  - Endpoint: `https://gamma-api.polymarket.com`
  - `/public-search` - Full-text market search
  - `/markets` - Market listings with prices
- **Polymarket CLOB API** - Order book data (fallback)
  - Endpoint: `https://clob.polymarket.com`
  - `/midpoint` - Mid price
  - `/book` - Bid/ask spreads

### Data Flow
/search bitcoin
↓
Gamma API public-search
↓
Save ALL tokens → search_cache
↓
Display to user
↓
User: /sub <token>
↓
Get from search_cache → Save to market_metadata
↓
Add subscription
↓
Hourly job reads market_metadata (fast!)
↓
Send updates with full context

## 📊 Update Format
📊 Polymarket Update
Market: Will Bitcoin hit $100k by year end?
Outcome: Yes
🔑 Token ID: 29763725280755533...
💰 Mid price: 0.65
📈 Best bid: 0.64 (size: 100)
📉 Best ask: 0.66 (size: 150)
📏 Spread: 2.0%
⏰ 2025-03-24 15:30:45 UTC

## 🐛 Troubleshooting

### Bot doesn't start
- Check your `TELEGRAM_TOKEN` in `.env`
- Verify token with [@BotFather](https://t.me/BotFather)
- Check Python version: `python --version` (must be 3.8+)

### "Unknown" market name in updates
- Run `/search` first to populate cache
- Subscribe immediately after search
- Market metadata is saved on first subscribe

### No hourly updates received
- Check bot logs for errors
- Verify subscription: `/status`
- Test manually: `/test`

## 🔒 Security

- ✅ Never commit `.env` to Git
- ✅ Use `.gitignore` to exclude secrets
- ✅ Revoke tokens if accidentally exposed
- ✅ Use pre-commit hooks to prevent leaks

## 📝 Development

### Add a new command
```python
async def my_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello!")

# In main()
application.add_handler(CommandHandler("mycommand", my_command))
```

### Modify update frequency
```python
# In post_init()
scheduler.add_job(
    job_send_updates,
    'interval',
    hours=2,  # Change from 1 to 2 hours
    # ...
)
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Commit changes: `git commit -m "Add feature"`
4. Push: `git push origin feature-name`
5. Open a Pull Request

## 📜 License

MIT License - feel free to use and modify!

## 🙏 Acknowledgments

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) - Telegram Bot framework
- [Polymarket](https://polymarket.com) - Prediction market platform
- [APScheduler](https://apscheduler.readthedocs.io/) - Job scheduling

## 📧 Support

For issues or questions:
- Open an issue on GitHub
- Check existing documentation
- Review troubleshooting section

---

**Happy trading! 📊💰**