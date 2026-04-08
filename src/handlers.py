import os
import json
import logging
import requests
from telegram import Update
from telegram.ext import ContextTypes

from .database import (
    add_subscription, remove_subscription, get_user_subscriptions,
    delete_all_user_subscriptions, clear_search_cache, save_to_search_cache,
    get_from_search_cache, save_market_metadata, get_market_metadata
)
from .poly_api import fetch_market_data, get_market_info_from_gamma, GAMMA_API
from .formatter import format_market_message, escape_markdown
from .wallet import PolyWallet, format_wallet_message

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message"""
    await update.message.reply_text(
        "👋 *Welcome to the Polymarket bot\\!*\n\n"
        "Available commands:\n"
        "• `/subscribe <token_id>` \\- Subscribe to a token\n"
        "• `/unsubscribe <token_id>` \\- Unsubscribe\n"
        "• `/status` \\- View your subscriptions\n"
        "• `/check <token_id>` \\- Check current price\n"
        "• `/search <term>` \\- Search for markets\n"
        "• `/reset` \\- Delete all your subscriptions\n"
        "• `/test` \\- Test immediate send \\(debug\\)\n"
        "• `/wallet` \\- Check wallet data \n\n"
        "💡 You will receive updates every hour\\.\n\n"
        "🔍 To find a token\\_id, use `/search` or go to "
        "polymarket\\.com and get the token from the market URL\\.",
        parse_mode='MarkdownV2'
    )


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Subscribe to a token"""
    if not context.args:
        await update.message.reply_text(
            "Usage: `/subscribe <token_id>`\n\n"
            "Example: `/subscribe 21742633143463906...`"
        )
        return

    token_id = context.args[0].strip()
    
    logger.info(f"Subscribe request from {update.effective_chat.id} for token: {token_id[:20]}... (length: {len(token_id)})")
    
    if token_id.endswith('...') or len(token_id) < 50:
        await update.message.reply_text(
            "❌ Token ID appears incomplete\\. "
            "Make sure to copy the full token ID from the search results\\.",
            parse_mode='MarkdownV2'
        )
        return
    
    # Get market info from search cache first
    market_info = get_from_search_cache(token_id)
    
    if market_info:
        logger.info(f"✅ Found token in search cache: {market_info.get('question', 'N/A')[:50]}")
        save_market_metadata(
            token_id,
            market_info["question"],
            market_info["outcome"],
            market_info["slug"],
            market_info.get("event_title", market_info["question"])
        )
    else:
        logger.warning(f"⚠️ Token NOT in search cache, checking permanent DB or Gamma API")
        market_info = get_market_info_from_gamma(token_id)
    
    # Verify token exists
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
    
    add_subscription(update.effective_chat.id, token_id)
    
    await update.message.reply_text(
        f"✅ Subscribed to token\\!\n\n"
        f"{format_market_message(info, market_info)}",
        parse_mode='MarkdownV2'
    )


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unsubscribe from a token"""
    if not context.args:
        await update.message.reply_text("Usage: `/unsubscribe <token_id>`", parse_mode='MarkdownV2')
        return

    token_id = context.args[0]
    remove_subscription(update.effective_chat.id, token_id)
    token_short = escape_markdown(token_id[:20] + "...")
    await update.message.reply_text(f"✅ Unsubscribed from token `{token_short}`", parse_mode='MarkdownV2')


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View user subscriptions"""
    rows = get_user_subscriptions(update.effective_chat.id)

    if not rows:
        await update.message.reply_text("You are not subscribed to any markets.")
    else:
        msg = "📋 *Your subscriptions:*\n\n"
        for token in rows:
            market_info = get_market_metadata(token)
            if market_info:
                question = escape_markdown(market_info.get('question', 'N/A')[:50] + "...")
                outcome = escape_markdown(market_info.get('outcome', 'N/A'))
                msg += f"• {outcome} \\- {question}\n"
            else:
                token_short = escape_markdown(token[:20] + "...")
                msg += f"• `{token_short}`\n"
        
        await update.message.reply_text(msg, parse_mode='MarkdownV2')


async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check current price without subscribing"""
    if not context.args:
        await update.message.reply_text("Usage: `/check <token_id>`", parse_mode='MarkdownV2')
        return

    token_id = context.args[0]
    info = fetch_market_data(token_id)
    market_info = get_market_info_from_gamma(token_id)
    msg = format_market_message(info, market_info)
    await update.message.reply_text(msg, parse_mode='MarkdownV2')


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete all subscriptions for this user"""
    chat_id = update.effective_chat.id
    
    rows = get_user_subscriptions(chat_id)
    count = len(rows)
    
    if count == 0:
        await update.message.reply_text(
            "You have no active subscriptions\\.",
            parse_mode='MarkdownV2'
        )
        return
    
    await update.message.reply_text(
        f"⚠️ Are you sure you want to delete *{count} subscription\\(s\\)*?\n\n"
        f"Send `/confirm_reset` to proceed or any other message to cancel\\.",
        parse_mode='MarkdownV2'
    )


async def confirm_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm and execute reset"""
    chat_id = update.effective_chat.id
    
    count = delete_all_user_subscriptions(chat_id)
    
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
    
    clear_search_cache()
    logger.info(f"🔍 Starting search for: {search_term}")
    
    try:
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
        
        msg = f"🔍 *{len(events)} result\\(s\\) for '{escape_markdown(search_term)}'*\n\n"
        MAX_LENGTH = 3800
        
        count = 0
        for event in events:
            logger.info(f"📋 Processing event {count+1}/{len(events)}: {event.get('title', 'N/A')[:50]}")
            
            if count >= 3:
                logger.info(f"⏭️ Skipping remaining events (limit reached)")
                break
            
            title = event.get("title", "N/A")
            markets = event.get("markets", [])
            
            logger.info(f"   Found {len(markets)} markets in this event")
            
            if not markets:
                logger.warning(f"   ⚠️ No markets in this event, skipping")
                continue
            
            title_short = title[:80] if len(title) <= 80 else title[:77] + "..."
            event_msg = f"📅 *{escape_markdown(title_short)}*\n"
            
            logger.info(f"   Processing up to 2 markets from this event...")
            
            markets_processed = 0
            for market in markets[:2]:
                markets_processed += 1
                
                question = market.get("question", "N/A")
                slug = market.get("slug", "")
                tokens_raw = market.get("clobTokenIds", [])
                outcomes_raw = market.get("outcomes", [])
                
                logger.info(f"   📝 Market {markets_processed}/2: {question[:40]}...")
                logger.info(f"      Raw tokens type: {type(tokens_raw)}")
                logger.info(f"      Raw outcomes type: {type(outcomes_raw)}")
                
                # Parse JSON strings
                tokens = []
                if isinstance(tokens_raw, str):
                    try:
                        tokens = json.loads(tokens_raw)
                        logger.info(f"      Parsed tokens from string: {len(tokens)} tokens")
                    except json.JSONDecodeError as e:
                        logger.error(f"      Failed to parse tokens: {e}")
                        tokens = []
                elif isinstance(tokens_raw, list):
                    tokens = tokens_raw
                    logger.info(f"      Tokens already list: {len(tokens)} tokens")
                
                outcomes = []
                if isinstance(outcomes_raw, str):
                    try:
                        outcomes = json.loads(outcomes_raw)
                        logger.info(f"      Parsed outcomes from string: {len(outcomes)} outcomes")
                    except json.JSONDecodeError as e:
                        logger.error(f"      Failed to parse outcomes: {e}")
                        outcomes = []
                elif isinstance(outcomes_raw, list):
                    outcomes = outcomes_raw
                    logger.info(f"      Outcomes already list: {len(outcomes)} outcomes")
                
                logger.info(f"      Final: {len(tokens)} tokens, {len(outcomes)} outcomes")
                
                # SAVE TO SEARCH CACHE
                saved_count = 0
                for i, token in enumerate(tokens):
                    outcome = outcomes[i] if i < len(outcomes) else "Unknown"
                    try:
                        save_to_search_cache(token, question, outcome, slug, title)
                        saved_count += 1
                        logger.info(f"      💾 Cached token {token[:20]}... ({outcome})")
                    except Exception as e:
                        logger.error(f"      ❌ Failed to cache token {token[:20]}...: {e}")
                
                logger.info(f"      ✅ Saved {saved_count}/{len(tokens)} tokens to cache")
                
                question_short = question if len(question) <= 50 else question[:47] + "..."
                event_msg += f"  ❓ {escape_markdown(question_short)}\n"
                
                if tokens and outcomes:
                    for i, token in enumerate(tokens[:2]):
                        outcome = outcomes[i] if i < len(outcomes) else "?"
                        event_msg += f"     • {escape_markdown(outcome)}: `/sub {token}`\n"
                else:
                    event_msg += f"     ⚠️  Unavailable\n"
            
            if len(markets) > 2:
                markets_diff = len(markets) - 2
                event_msg += f"  _{markets_diff} other market\\(s\\)_\n"
            
            event_msg += "\n"
            
            new_length = len(msg + event_msg)
            logger.info(f"   Message length: {new_length}/{MAX_LENGTH}")
            
            if new_length > MAX_LENGTH:
                logger.warning(f"   ⚠️ Message too long, stopping here")
                break
            
            msg += event_msg
            count += 1
            logger.info(f"   ✅ Event added to message (total events: {count})")
        
        if len(events) > count:
            events_diff = len(events) - count
            msg += f"_{events_diff} other event\\(s\\)_\n"
        
        msg += f"\n💡 Use `/sub <token>` to subscribe"
        
        # Final verification
        from .database import DB_PATH
        import sqlite3
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM search_cache")
        total_cached = cur.fetchone()[0]
        con.close()
        
        logger.info(f"✅ Search completed - {total_cached} tokens in cache")
        await update.message.reply_text(msg, parse_mode='MarkdownV2')
        
    except Exception as e:
        logger.exception(f"Error during search: {e}")
        await update.message.reply_text("❌ Error searching markets.")


async def test_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually trigger update sending"""
    await update.message.reply_text("🔄 Sending updates...")
    
    from main import job_send_updates
    application = context.application
    await job_send_updates(application)
    
    await update.message.reply_text("✅ Updates sent!")

async def wallet_info(update, context):
    wallet = PolyWallet(os.getenv("POLY_FUNDER_ADDRESS"))
    summary = wallet.get_summary()
    msg = format_wallet_message(summary)
    await update.message.reply_text(msg, parse_mode='HTML')