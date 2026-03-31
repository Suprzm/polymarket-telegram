import json
from telegram import Update
from telegram.ext import ContextTypes
from src.database import *
from src.poly_api import *
from src.formatter import format_market_message

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 <b>Bot Polymarket</b>\n/search [terme]\n/sub [token_id]\n/status", parse_mode='HTML')

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query: return
    
    events = public_search(query)
    if not events:
        await update.message.reply_text("Aucun résultat.")
        return

    msg = f"🔍 <b>Résultats pour '{query}'</b>\n\n"
    for ev in events[:3]:
        msg += f"📅 <b>{ev['title']}</b>\n"
        for m in ev.get('markets', [])[:2]:
            tokens = json.loads(m['clobTokenIds']) if isinstance(m['clobTokenIds'], str) else m['clobTokenIds']
            outcomes = json.loads(m['outcomes']) if isinstance(m['outcomes'], str) else m['outcomes']
            for i, tid in enumerate(tokens[:2]):
                save_metadata(tid, m['question'], outcomes[i], ev['slug'], ev['title'], table="search_cache")
                msg += f"  • {outcomes[i]}: <code>{tid}</code>\n"
        msg += "\n"
    await update.message.reply_text(msg, parse_mode='HTML')

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    tid = context.args[0]
    add_subscription(update.effective_chat.id, tid)
    
    info = fetch_market_data(tid)
    meta = get_metadata(tid)
    if meta: save_metadata(tid, meta['question'], meta['outcome'], meta['slug'], meta['event_title'])
    
    await update.message.reply_text(f"✅ Abonné !\n\n{format_market_message(info, meta)}", parse_mode='HTML')

async def job_send_updates(application):
    tokens = list_tokens()
    for tid in tokens:
        info = fetch_market_data(tid)
        meta = get_metadata(tid)
        msg = format_market_message(info, meta)
        for cid in list_subscribers(tid):
            try: await application.bot.send_message(chat_id=cid, text=msg, parse_mode='HTML')
            except: pass