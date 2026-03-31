import os
import sqlite3
import logging
import requests
import asyncio
import json
from datetime import datetime
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- Setup ---
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TELEGRAM_TOKEN:
    raise SystemExit("TELEGRAM_TOKEN missing in .env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "subscriptions.db"

# Official Polymarket API URLs
CLOB_API = "https://clob.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"


# --- DB helpers -------------------------------------------------------------
def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    
    # Table for subscriptions
    cur.execute("""
    CREATE TABLE IF NOT EXISTS subscriptions (
        chat_id TEXT,
        token_id TEXT,
        PRIMARY KEY (chat_id, token_id)
    )
    """)
    
    # Table for market metadata (permanent storage)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS market_metadata (
        token_id TEXT PRIMARY KEY,
        question TEXT,
        outcome TEXT,
        slug TEXT,
        event_title TEXT,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Temporary table for search results (cleared on each search)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS search_cache (
        token_id TEXT PRIMARY KEY,
        question TEXT,
        outcome TEXT,
        slug TEXT,
        event_title TEXT,
        cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    con.commit()
    con.close()

def clear_search_cache():
    """Clear temporary search cache"""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("DELETE FROM search_cache")
    con.commit()
    con.close()
    logger.info("🗑️ Search cache cleared")

def save_to_search_cache(token_id: str, question: str, outcome: str, slug: str, event_title: str):
    """Save market info to temporary search cache"""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO search_cache (token_id, question, outcome, slug, event_title)
        VALUES (?, ?, ?, ?, ?)
    """, (token_id, question, outcome, slug, event_title))
    con.commit()
    con.close()

def get_from_search_cache(token_id: str):
    """Get market info from search cache"""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        SELECT question, outcome, slug, event_title FROM search_cache WHERE token_id = ?
    """, (token_id,))
    row = cur.fetchone()
    
    # DEBUG: Log cache contents
    cur.execute("SELECT COUNT(*) FROM search_cache")
    total = cur.fetchone()[0]
    logger.info(f"🔍 Search cache contains {total} tokens")
    
    con.close()
    
    if row:
        logger.info(f"✅ Cache HIT for token {token_id[:20]}...")
        return {
            "question": row[0],
            "outcome": row[1],
            "slug": row[2],
            "event_title": row[3]
        }
    else:
        logger.warning(f"❌ Cache MISS for token {token_id[:20]}...")
        # DEBUG: Show some tokens in cache
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT token_id FROM search_cache LIMIT 3")
        samples = [r[0][:20] + "..." for r in cur.fetchall()]
        logger.info(f"Sample tokens in cache: {samples}")
        con.close()
        return None

def save_market_metadata(token_id: str, question: str, outcome: str, slug: str, event_title: str):
    """Save market metadata to permanent storage"""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO market_metadata (token_id, question, outcome, slug, event_title)
        VALUES (?, ?, ?, ?, ?)
    """, (token_id, question, outcome, slug, event_title))
    con.commit()
    con.close()
    logger.info(f"💾 Saved metadata for token {token_id[:20]}...")

def get_market_metadata(token_id: str):
    """Get market metadata from permanent storage"""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        SELECT question, outcome, slug, event_title FROM market_metadata WHERE token_id = ?
    """, (token_id,))
    row = cur.fetchone()
    con.close()
    
    if row:
        return {
            "question": row[0],
            "outcome": row[1],
            "slug": row[2],
            "event_title": row[3]
        }
    return None

def add_subscription(chat_id: int, token_id: str):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO subscriptions(chat_id, token_id) VALUES (?, ?)",
                (str(chat_id), token_id))
    con.commit()
    con.close()

def remove_subscription(chat_id: int, token_id: str):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("DELETE FROM subscriptions WHERE chat_id=? AND token_id=?",
                (str(chat_id), token_id))
    con.commit()
    con.close()

def list_subscribers_for_token(token_id: str):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT chat_id FROM subscriptions WHERE token_id=?", (token_id,))
    rows = [r[0] for r in cur.fetchall()]
    con.close()
    return rows

def list_tokens():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT DISTINCT token_id FROM subscriptions")
    rows = [r[0] for r in cur.fetchall()]
    con.close()
    return rows


def escape_markdown(text: str) -> str:
    """Escape special characters for Markdown V2"""
    if text is None:
        return "N/A"
    
    text = str(text)  # Convert to string first
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


# --- Fetch Polymarket (Official CLOB API) -----------------------------------
def fetch_market_data(token_id: str):
    """
    Fetch market data for a token via Polymarket's Gamma API.
    The Gamma API has outcomePrices which is more reliable than CLOB for all markets.
    """
    try:
        # Clean token_id (remove any trailing dots or whitespace)
        token_id = str(token_id).strip().rstrip('.')
        
        logger.info(f"Fetching data for token: {token_id}")
        
        # Use Gamma API to find the market with this token
        # Try both active and all markets
        url = f"{GAMMA_API}/markets"
        params = {"limit": 100}  # Remove active filter to search all markets
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        markets = resp.json()
        
        # Find the market containing this token
        for market in markets:
            clob_token_ids_raw = market.get("clobTokenIds", [])
            
            # Parse JSON string if needed
            clob_token_ids = []
            if isinstance(clob_token_ids_raw, str):
                try:
                    clob_token_ids = json.loads(clob_token_ids_raw)
                except json.JSONDecodeError:
                    continue
            elif isinstance(clob_token_ids_raw, list):
                clob_token_ids = clob_token_ids_raw
            
            if token_id in clob_token_ids:
                # Found the market! Get prices from outcomePrices
                outcome_prices_raw = market.get("outcomePrices", [])
                outcomes_raw = market.get("outcomes", [])
                
                # Parse JSON strings
                outcome_prices = []
                if isinstance(outcome_prices_raw, str):
                    try:
                        outcome_prices = json.loads(outcome_prices_raw)
                    except json.JSONDecodeError:
                        outcome_prices = []
                elif isinstance(outcome_prices_raw, list):
                    outcome_prices = outcome_prices_raw
                
                outcomes = []
                if isinstance(outcomes_raw, str):
                    try:
                        outcomes = json.loads(outcomes_raw)
                    except json.JSONDecodeError:
                        outcomes = []
                elif isinstance(outcomes_raw, list):
                    outcomes = outcomes_raw
                
                # Get the index of this token
                token_index = clob_token_ids.index(token_id)
                price = float(outcome_prices[token_index]) if token_index < len(outcome_prices) else None
                
                # Try to get additional data from CLOB (optional, may fail for some markets)
                best_bid = None
                best_ask = None
                bid_size = None
                ask_size = None
                
                try:
                    book_url = f"{CLOB_API}/book"
                    book_params = {"token_id": token_id}
                    book_resp = requests.get(book_url, params=book_params, timeout=5)
                    if book_resp.status_code == 200:
                        book_data = book_resp.json()
                        bids = book_data.get("bids", [])
                        asks = book_data.get("asks", [])
                        
                        best_bid = float(bids[0]["price"]) if bids else None
                        best_ask = float(asks[0]["price"]) if asks else None
                        bid_size = float(bids[0]["size"]) if bids else None
                        ask_size = float(asks[0]["size"]) if asks else None
                except:
                    pass  # CLOB data not available, that's okay
                
                # Calculate spread if we have bid/ask
                spread = None
                if best_bid and best_ask:
                    spread = round((best_ask - best_bid) * 100, 2)
                
                return {
                    "token_id": token_id,
                    "mid_price": price,  # Use Gamma price as mid
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "bid_size": bid_size,
                    "ask_size": ask_size,
                    "spread": spread,
                }
        
        # Token not found in first batch, search more extensively
        logger.info(f"Token not found in first 100 markets, searching more...")
        for offset in [100, 200, 300, 400, 500]:
            params = {"limit": 100, "offset": offset}
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                break
            
            markets = resp.json()
            if not markets:
                break
            
            for market in markets:
                clob_token_ids_raw = market.get("clobTokenIds", [])
                
                clob_token_ids = []
                if isinstance(clob_token_ids_raw, str):
                    try:
                        clob_token_ids = json.loads(clob_token_ids_raw)
                    except json.JSONDecodeError:
                        continue
                elif isinstance(clob_token_ids_raw, list):
                    clob_token_ids = clob_token_ids_raw
                
                if token_id in clob_token_ids:
                    # Same logic as above
                    outcome_prices_raw = market.get("outcomePrices", [])
                    
                    outcome_prices = []
                    if isinstance(outcome_prices_raw, str):
                        try:
                            outcome_prices = json.loads(outcome_prices_raw)
                        except json.JSONDecodeError:
                            outcome_prices = []
                    elif isinstance(outcome_prices_raw, list):
                        outcome_prices = outcome_prices_raw
                    
                    token_index = clob_token_ids.index(token_id)
                    price = float(outcome_prices[token_index]) if token_index < len(outcome_prices) else None
                    
                    return {
                        "token_id": token_id,
                        "mid_price": price,
                        "best_bid": None,
                        "best_ask": None,
                        "bid_size": None,
                        "ask_size": None,
                        "spread": None,
                    }
        
        logger.error(f"Token {token_id} not found in any markets")
        
        # Last resort: try to get data from CLOB even if market not in Gamma
        logger.info(f"Attempting direct CLOB lookup as fallback...")
        try:
            mid_url = f"{CLOB_API}/midpoint"
            mid_params = {"token_id": token_id}
            mid_resp = requests.get(mid_url, params=mid_params, timeout=10)
            
            if mid_resp.status_code == 200:
                mid_data = mid_resp.json()
                mid_price = mid_data.get("mid")
                
                # Get order book
                book_url = f"{CLOB_API}/book"
                book_params = {"token_id": token_id}
                book_resp = requests.get(book_url, params=book_params, timeout=10)
                
                if book_resp.status_code == 200:
                    book_data = book_resp.json()
                    bids = book_data.get("bids", [])
                    asks = book_data.get("asks", [])
                    
                    best_bid = float(bids[0]["price"]) if bids else None
                    best_ask = float(asks[0]["price"]) if asks else None
                    bid_size = float(bids[0]["size"]) if bids else None
                    ask_size = float(asks[0]["size"]) if asks else None
                    
                    spread = None
                    if best_bid and best_ask:
                        spread = round((best_ask - best_bid) * 100, 2)
                    
                    logger.info(f"Found token data in CLOB directly")
                    return {
                        "token_id": token_id,
                        "mid_price": mid_price,
                        "best_bid": best_bid,
                        "best_ask": best_ask,
                        "bid_size": bid_size,
                        "ask_size": ask_size,
                        "spread": spread,
                    }
        except Exception as e:
            logger.warning(f"CLOB fallback also failed: {e}")
        
        return None

    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP Error for token {token_id}: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        logger.exception(f"Error in fetch_market_data for token {token_id}: {e}")
        return None


# Cache pour éviter de chercher plusieurs fois le même token
# NOW REPLACED BY DATABASE - keeping for backwards compatibility
_market_info_cache = {}

def get_market_info_from_gamma(token_id: str):
    """
    Fetch market info from DB first, then Gamma API if needed.
    Priority: permanent DB > search cache > Gamma API
    """
    # 1. Check permanent storage first
    metadata = get_market_metadata(token_id)
    if metadata:
        logger.info(f"✅ Found metadata in permanent DB for token {token_id[:20]}...")
        return metadata
    
    # 2. Check search cache
    metadata = get_from_search_cache(token_id)
    if metadata:
        logger.info(f"✅ Found metadata in search cache for token {token_id[:20]}...")
        return metadata
    
    # 3. Check memory cache (backwards compatibility)
    if token_id in _market_info_cache:
        logger.info(f"✅ Found metadata in memory cache for token {token_id[:20]}...")
        return _market_info_cache[token_id]
    
    # 4. Fall back to Gamma API search
    logger.info(f"🔍 Searching Gamma API for token {token_id[:20]}...")
    
    try:
        url = f"{GAMMA_API}/markets"
        
        # Try multiple pages to find the token
        for offset in range(0, 1000, 100):
            params = {"limit": 100, "offset": offset}
            resp = requests.get(url, params=params, timeout=10)
            
            if resp.status_code != 200:
                break
                
            markets = resp.json()
            if not markets:
                break
            
            for market in markets:
                clob_token_ids_raw = market.get("clobTokenIds", [])
                outcomes_raw = market.get("outcomes", [])
                
                clob_token_ids = []
                if isinstance(clob_token_ids_raw, str):
                    try:
                        clob_token_ids = json.loads(clob_token_ids_raw)
                    except json.JSONDecodeError:
                        continue
                elif isinstance(clob_token_ids_raw, list):
                    clob_token_ids = clob_token_ids_raw
                
                outcomes = []
                if isinstance(outcomes_raw, str):
                    try:
                        outcomes = json.loads(outcomes_raw)
                    except json.JSONDecodeError:
                        outcomes = []
                elif isinstance(outcomes_raw, list):
                    outcomes = outcomes_raw
                
                if token_id in clob_token_ids:
                    token_index = clob_token_ids.index(token_id)
                    outcome = outcomes[token_index] if token_index < len(outcomes) else "Unknown"
                    
                    result = {
                        "question": market.get("question", "N/A"),
                        "outcome": outcome,
                        "slug": market.get("slug", ""),
                        "event_title": market.get("question", "N/A")  # Use question as event title
                    }
                    
                    # Save to permanent DB for future use
                    save_market_metadata(
                        token_id,
                        result["question"],
                        result["outcome"],
                        result["slug"],
                        result["event_title"]
                    )
                    
                    logger.info(f"✅ Found and saved metadata from Gamma API")
                    return result
        
        logger.warning(f"❌ Token {token_id[:20]}... not found in Gamma API")
        return None
        
    except Exception as e:
        logger.exception(f"Error in get_market_info_from_gamma: {e}")
        return None


# --- Formatting -------------------------------------------------------------
def format_market_message(info: dict, market_info: dict = None):
    if not info:
        return "❌ Error: unable to fetch market data\\."

    lines = ["📊 *Polymarket Update*", ""]
    
    # Always show market info if available
    if market_info:
        question = escape_markdown(market_info.get('question', 'N/A'))
        outcome = escape_markdown(market_info.get('outcome', 'N/A'))
        lines.extend([
            f"*Market:* {question}",
            f"*Outcome:* {outcome}",
            ""
        ])
    else:
        # If no market info, at least show we're trying to get it
        lines.append("*Market:* Unknown")
        lines.append("")
    
    token_short = escape_markdown(str(info.get('token_id', 'N/A'))[:20] + "...")
    mid = escape_markdown(info.get('mid_price') if info.get('mid_price') is not None else 'N/A')
    bid = escape_markdown(info.get('best_bid') if info.get('best_bid') is not None else 'N/A')
    ask = escape_markdown(info.get('best_ask') if info.get('best_ask') is not None else 'N/A')
    bid_size = escape_markdown(info.get('bid_size') if info.get('bid_size') is not None else 'N/A')
    ask_size = escape_markdown(info.get('ask_size') if info.get('ask_size') is not None else 'N/A')
    
    lines.extend([
        f"🔑 *Token ID:* `{token_short}`",
        "",
        f"💰 *Mid price:* {mid}",
        f"📈 *Best bid:* {bid} \\(size: {bid_size}\\)",
        f"📉 *Best ask:* {ask} \\(size: {ask_size}\\)",
    ])
    
    if info.get('spread') is not None:
        spread = escape_markdown(info.get('spread'))
        lines.append(f"📏 *Spread:* {spread}%")
    
    # Format timestamp carefully
    timestamp_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    timestamp = escape_markdown(timestamp_str)
    lines.extend([
        "",
        f"⏰ {timestamp} UTC"
    ])
    
    return "\n".join(lines)


# --- Periodic Job -----------------------------------------------------------
async def job_send_updates(application):
    logger.info("⏱️ Running hourly job…")

    tokens = list_tokens()
    if not tokens:
        logger.info("No subscriptions at the moment.")
        return

    for token_id in tokens:
        info = fetch_market_data(token_id)
        market_info = get_market_info_from_gamma(token_id)
        msg = format_market_message(info, market_info)
        subscribers = list_subscribers_for_token(token_id)

        for chat_id in subscribers:
            try:
                await application.bot.send_message(
                    chat_id=int(chat_id), 
                    text=msg,
                    parse_mode='MarkdownV2'
                )
                logger.info(f"✅ Message sent to {chat_id}")
            except Exception as e:
                logger.warning(f"❌ Error sending to {chat_id}: {e}")


# --- Telegram Handlers ------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Welcome to the Polymarket bot\\!*\n\n"
        "Available commands:\n"
        "• `/subscribe <token_id>` \\- Subscribe to a token\n"
        "• `/unsubscribe <token_id>` \\- Unsubscribe\n"
        "• `/status` \\- View your subscriptions\n"
        "• `/check <token_id>` \\- Check current price\n"
        "• `/search <term>` \\- Search for markets\n"
        "• `/reset` \\- Delete all your subscriptions\n"
        "• `/test` \\- Test immediate send \\(debug\\)\n\n"
        "💡 You will receive updates every hour\\.\n\n"
        "🔍 To find a token\\_id, use `/search` or go to "
        "polymarket\\.com and get the token from the market URL\\.",
        parse_mode='MarkdownV2'
    )

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: `/subscribe <token_id>`\n\n"
            "Example: `/subscribe 21742633143463906...`"
        )
        return

    token_id = context.args[0].strip()
    
    # Log for debugging
    logger.info(f"Subscribe request from {update.effective_chat.id} for token: {token_id[:20]}... (length: {len(token_id)})")
    
    # Check if token_id looks truncated
    if token_id.endswith('...') or len(token_id) < 50:
        await update.message.reply_text(
            "❌ Token ID appears incomplete\\. "
            "Make sure to copy the full token ID from the search results\\.",
            parse_mode='MarkdownV2'
        )
        return
    
    # Get market info from search cache first (most recent search)
    market_info = get_from_search_cache(token_id)
    
    if market_info:
        logger.info(f"✅ Found token in search cache: {market_info.get('question', 'N/A')[:50]}")
        # Save to permanent storage
        save_market_metadata(
            token_id,
            market_info["question"],
            market_info["outcome"],
            market_info["slug"],
            market_info.get("event_title", market_info["question"])
        )
    else:
        # Try permanent DB or Gamma API
        logger.warning(f"⚠️ Token NOT in search cache, checking permanent DB or Gamma API")
        market_info = get_market_info_from_gamma(token_id)
    
    # Verify token exists by fetching price data
    info = fetch_market_data(token_id)
    if not info:
        token_short = escape_markdown(token_id[:20] + "...")
        await update.message.reply_text(
            f"❌ Unable to fetch data for token `{token_short}`\n"
            "The token ID may be invalid or the market may be closed\\.\n"
            "Try using `/search` to find an active market\\.",
            parse_mode='MarkdownV2'
        )
        return
    
    # Add subscription
    add_subscription(update.effective_chat.id, token_id)
    
    await update.message.reply_text(
        f"✅ Subscribed to token\\!\n\n"
        f"{format_market_message(info, market_info)}",
        parse_mode='MarkdownV2'
    )

async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/unsubscribe <token_id>`", parse_mode='MarkdownV2')
        return

    token_id = context.args[0]
    remove_subscription(update.effective_chat.id, token_id)
    token_short = escape_markdown(token_id[:20] + "...")
    await update.message.reply_text(f"✅ Unsubscribed from token `{token_short}`", parse_mode='MarkdownV2')

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT token_id FROM subscriptions WHERE chat_id=?",
                (str(update.effective_chat.id),))
    rows = [r[0] for r in cur.fetchall()]
    con.close()

    if not rows:
        await update.message.reply_text("You are not subscribed to any markets.")
    else:
        msg = "📋 *Your subscriptions:*\n\n"
        for token in rows:
            # Get market info
            market_info = get_market_info_from_gamma(token)
            if market_info:
                question = escape_markdown(market_info.get('question', 'N/A')[:50] + "...")
                outcome = escape_markdown(market_info.get('outcome', 'N/A'))
                msg += f"• {outcome} \\- {question}\n"
            else:
                token_short = escape_markdown(token[:20] + "...")
                msg += f"• `{token_short}`\n"
        
        await update.message.reply_text(msg, parse_mode='MarkdownV2')

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check current price of a token without subscribing"""
    if not context.args:
        await update.message.reply_text("Usage: `/check <token_id>`", parse_mode='MarkdownV2')
        return

    token_id = context.args[0]
    info = fetch_market_data(token_id)
    market_info = get_market_info_from_gamma(token_id)
    msg = format_market_message(info, market_info)
    await update.message.reply_text(msg, parse_mode='MarkdownV2')

async def test_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually trigger update sending (for testing)"""
    await update.message.reply_text("🔄 Sending updates...")
    
    # Get application from context
    application = context.application
    await job_send_updates(application)
    
    await update.message.reply_text("✅ Updates sent!")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete all subscriptions for this user"""
    chat_id = update.effective_chat.id
    
    # Get current subscriptions count
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM subscriptions WHERE chat_id=?", (str(chat_id),))
    count = cur.fetchone()[0]
    con.close()
    
    if count == 0:
        await update.message.reply_text(
            "You have no active subscriptions\\.",
            parse_mode='MarkdownV2'
        )
        return
    
    # Ask for confirmation
    await update.message.reply_text(
        f"⚠️ Are you sure you want to delete *{count} subscription\\(s\\)*?\n\n"
        f"Send `/confirm_reset` to proceed or any other message to cancel\\.",
        parse_mode='MarkdownV2'
    )

async def confirm_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm and execute reset"""
    chat_id = update.effective_chat.id
    
    # Delete all subscriptions for this user
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM subscriptions WHERE chat_id=?", (str(chat_id),))
    count = cur.fetchone()[0]
    
    cur.execute("DELETE FROM subscriptions WHERE chat_id=?", (str(chat_id),))
    con.commit()
    con.close()
    
    logger.info(f"🗑️ User {chat_id} deleted {count} subscription(s)")
    
    await update.message.reply_text(
        f"✅ Successfully deleted *{count} subscription\\(s\\)*\\!\n\n"
        f"Use `/search` to find new markets\\.",
        parse_mode='MarkdownV2'
    )

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search for Polymarket markets"""
    if not context.args:
        await update.message.reply_text(
            "Usage: `/search <term>`\n\n"
            "Example: `/search bitcoin` or `/search trump` or `/search paris`",
            parse_mode='MarkdownV2'
        )
        return

    search_term = " ".join(context.args)
    
    try:
        # Use official search endpoint
        url = f"{GAMMA_API}/public-search"
        params = {"q": search_term}
        
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        events = data.get("events", [])
        
        logger.info(f"📊 Found {len(events)} events from API")
        
        if not events:
            await update.message.reply_text(
                f"❌ No results found for '{escape_markdown(search_term)}'\\.",
                parse_mode='MarkdownV2'
            )
            return
        
        # Build message with size limit
        msg = f"🔍 *{len(events)} result\\(s\\) for '{escape_markdown(search_term)}'*\n\n"
        MAX_LENGTH = 3800  # Safety limit under Telegram's 4096
        
        count = 0
        for event in events:
            if count >= 3:  # Limit to 3 events instead of 5
                break
            
            title = event.get("title", "N/A")
            markets = event.get("markets", [])
            
            if not markets:
                continue
            
            # Build block for this event
            title_short = title[:80] if len(title) <= 80 else title[:77] + "..."
            event_msg = f"📅 *{escape_markdown(title_short)}*\n"
            
            # Limit to 2 markets per event
            for market in markets[:2]:
                question = market.get("question", "N/A")
                tokens_raw = market.get("clobTokenIds", [])
                outcomes_raw = market.get("outcomes", [])
                
                # Parse JSON strings
                tokens = []
                if isinstance(tokens_raw, str):
                    try:
                        tokens = json.loads(tokens_raw)
                    except json.JSONDecodeError:
                        tokens = []
                elif isinstance(tokens_raw, list):
                    tokens = tokens_raw
                
                outcomes = []
                if isinstance(outcomes_raw, str):
                    try:
                        outcomes = json.loads(outcomes_raw)
                    except json.JSONDecodeError:
                        outcomes = []
                elif isinstance(outcomes_raw, list):
                    outcomes = outcomes_raw
                
                # Shorten question
                question_short = question if len(question) <= 50 else question[:47] + "..."
                event_msg += f"  ❓ {escape_markdown(question_short)}\n"
                
                if tokens and outcomes:
                    # Show only first 2 outcomes with FULL token IDs (no truncation)
                    for i, token in enumerate(tokens[:2]):
                        outcome = outcomes[i] if i < len(outcomes) else "?"
                        # Don't truncate token_id - show it in full for the command to work
                        event_msg += f"     • {escape_markdown(outcome)}: `/sub {token}`\n"
                else:
                    event_msg += f"     ⚠️  Unavailable\n"
            
            if len(markets) > 2:
                markets_diff = len(markets) - 2
                event_msg += f"  _{markets_diff} other market\\(s\\)_\n"
            
            event_msg += "\n"
            
            # Check if we exceed limit
            if len(msg + event_msg) > MAX_LENGTH:
                break
            
            msg += event_msg
            count += 1
        
        if len(events) > count:
            events_diff = len(events) - count
            msg += f"_{events_diff} other event\\(s\\)_\n"
        
        msg += f"\n💡 Use `/sub <token>` to subscribe"
        
        await update.message.reply_text(msg, parse_mode='MarkdownV2')
        
    except Exception as e:
        logger.exception(f"Error during search: {e}")
        await update.message.reply_text("❌ Error searching markets.")


# --- Main -------------------------------------------------------------------
async def post_init(application):
    """Function called after application initialization"""
    # Configure scheduler for hourly updates
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        job_send_updates,
        'interval',
        hours=1,
        args=[application],
        id='hourly_updates',
        misfire_grace_time=300,  # 5 minutes grace if job is missed
        coalesce=True  # Merge missed executions into one
    )
    scheduler.start()
    logger.info("✅ Scheduler started - updates every hour")

def main():
    # Initialize database
    init_db()
    
    # Create application
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("subscribe", subscribe))
    application.add_handler(CommandHandler("sub", subscribe))  # Short alias
    application.add_handler(CommandHandler("unsubscribe", unsubscribe))
    application.add_handler(CommandHandler("unsub", unsubscribe))  # Short alias
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("check", check))
    application.add_handler(CommandHandler("search", search))
    application.add_handler(CommandHandler("test", test_job))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("confirm_reset", confirm_reset))
    
    # Start bot
    logger.info("🤖 Polymarket bot started")
    application.run_polling()

if __name__ == "__main__":
    main()