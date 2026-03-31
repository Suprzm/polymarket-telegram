import os
import logging
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import ApplicationBuilder, CommandHandler
from src.database import init_db
from src import handlers

load_dotenv()
logging.basicConfig(level=logging.INFO)

async def post_init(application):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(handlers.job_send_updates, 'interval', hours=1, args=[application])
    scheduler.start()

def main():
    if not os.path.exists("data"): os.makedirs("data")
    init_db()
    
    app = ApplicationBuilder().token(os.getenv("TELEGRAM_TOKEN")).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("search", handlers.search))
    app.add_handler(CommandHandler("sub", handlers.subscribe))
    app.add_handler(CommandHandler("subscribe", handlers.subscribe))
    app.add_handler(CommandHandler("test", lambda u, c: handlers.job_send_updates(c.application)))

    print("🤖 Bot démarré...")
    app.run_polling()

if __name__ == "__main__":
    main()