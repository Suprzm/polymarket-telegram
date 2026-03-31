# 🤖 Polymarket Telegram Bot

A modular Telegram bot for tracking Polymarket prediction markets with hourly price updates.

## ✨ Features

- 🔍 **Search Markets** - Find markets by keyword
- 📊 **Subscribe to Updates** - Get hourly price notifications
- 💰 **Real-time Prices** - Check current market prices
- 🗄️ **Smart Caching** - 3-tier database system for fast lookups
- 📈 **Detailed Info** - Market name, outcome, bid/ask, spread, timestamp
- 🏗️ **Modular Architecture** - Clean, maintainable codebase

## 📁 Project Structure
polymarket/
├── src/
│   ├── init.py       # Package initialization
│   ├── database.py       # Database operations
│   ├── poly_api.py       # Polymarket API interactions
│   ├── formatter.py      # Message formatting
│   └── handlers.py       # Telegram command handlers
├── data/
│   └── subscriptions.db  # SQLite database (auto-created)
├── venv/                 # Virtual environment
├── .env                  # Environment variables (not committed)
├── .env.example          # Template for .env
├── .gitignore           # Git ignore rules
├── main.py              # Application entry point
├── README.md            # This file
└── requirements.txt     # Python dependencies

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.8 or higher
- Telegram account
- Telegram Bot Token (get from [@BotFather](https://t.me/BotFather))

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/polymarket.git
cd polymarket

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
nano .env  # Add your TELEGRAM_TOKEN
```

### 3. Run the Bot
```bash
python main.py
```

You should see:
INFO:main:🤖 Polymarket bot started
INFO:main:✅ Scheduler started - updates every hour

## 📱 Bot Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/start` | Welcome message and help | `/start` |
| `/search <term>` | Search for markets | `/search bitcoin` |
| `/subscribe <token_id>` | Subscribe to updates | `/subscribe 297637...` |
| `/sub <token_id>` | Short alias for subscribe | `/sub 297637...` |
| `/unsubscribe <token_id>` | Unsubscribe | `/unsubscribe 297637...` |
| `/unsub <token_id>` | Short alias for unsubscribe | `/unsub 297637...` |
| `/status` | View your subscriptions | `/status` |
| `/check <token_id>` | Check current price | `/check 297637...` |
| `/reset` | Delete all subscriptions | `/reset` |
| `/test` | Manually trigger updates (debug) | `/test` |

## 🎯 Usage Example

Search for a market:
/search trump
Bot shows results:
📅 US Presidential Election
❓ Will Trump win 2024?
• Yes: /sub 29763725280755533...
• No: /sub 15902934770940509...
Subscribe:
/sub 29763725280755533...
Receive hourly updates! 🎉


## 🗄️ Database Architecture

### Three-tier caching system:

1. **`search_cache`** (temporary)
   - Cleared on each `/search`
   - Stores ALL tokens found
   - Fast subscription lookups

2. **`market_metadata`** (permanent)
   - Populated from search_cache on `/subscribe`
   - Persistent market information
   - Used for hourly updates

3. **`subscriptions`**
   - Links users to tokens
   - Core subscription tracking

## 🔧 Module Overview

### `src/database.py`
All database operations: subscriptions, caching, metadata management.

### `src/poly_api.py`
Polymarket API interactions: market data, prices, token lookups.

### `src/formatter.py`
Message formatting: Markdown escaping, price display.

### `src/handlers.py`
Telegram command handlers: search, subscribe, status, etc.

### `main.py`
Application entry point: bot initialization, scheduler, main loop.

## 🔒 Security

- ✅ Never commit `.env` to Git
- ✅ Use `.gitignore` to exclude secrets
- ✅ Revoke tokens if accidentally exposed
- ✅ Use environment variables for all secrets

## 📝 Development

### Running in development
```bash
# Activate virtual environment
source venv/bin/activate

# Run with debug logging
python main.py
```

### Adding a new command

1. Create handler in `src/handlers.py`:
```python
async def my_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello!")
```

2. Register in `main.py`:
```python
application.add_handler(CommandHandler("mycommand", my_command))
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

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- [Polymarket](https://polymarket.com)
- [APScheduler](https://apscheduler.readthedocs.io/)

---

**Happy trading! 📊💰**