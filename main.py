import os
import logging
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import ApplicationBuilder, CommandHandler

from src.database import init_db, list_tokens, list_subscribers_for_token
from src.poly_api import fetch_market_data, get_market_info_from_gamma
from src.formatter import format_market_message
from src.handlers import (
    start, subscribe, unsubscribe, status, check,
    reset, confirm_reset, search, test_job, wallet_info, startmm, stopmm, mmstatus
)


# Setup
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TELEGRAM_TOKEN:
    raise SystemExit("TELEGRAM_TOKEN missing in .env")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def job_send_updates(application):
    """Periodic job to send updates"""
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


async def post_init(application):
    """Initialize scheduler after app starts"""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        job_send_updates,
        'interval',
        hours=1,
        args=[application],
        id='hourly_updates',
        misfire_grace_time=300,
        coalesce=True
    )
    scheduler.start()
    logger.info("✅ Scheduler started - updates every hour")


def main():
    """Main entry point"""
    # Create data directory if it doesn't exist
    os.makedirs("data", exist_ok=True)
    
    # Initialize database
    init_db()
    
    # Create application
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("subscribe", subscribe))
    application.add_handler(CommandHandler("sub", subscribe))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe))
    application.add_handler(CommandHandler("unsub", unsubscribe))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("check", check))
    application.add_handler(CommandHandler("search", search))
    application.add_handler(CommandHandler("test", test_job))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("confirm_reset", confirm_reset))
    application.add_handler(CommandHandler("wallet", wallet_info))
    application.add_handler(CommandHandler("startmm", startmm))
    application.add_handler(CommandHandler("stopmm", stopmm))
    application.add_handler(CommandHandler("mmstatus", mmstatus))
    
    # Start bot
    logger.info("🤖 Polymarket bot started")
    application.run_polling()


if __name__ == "__main__":
    main()