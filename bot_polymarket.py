import os
import sqlite3
import logging
import requests
import json
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- Configuration & Setup ---
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TELEGRAM_TOKEN:
    raise SystemExit("ERREUR : TELEGRAM_TOKEN manquant dans le fichier .env")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_PATH = "subscriptions.db"
CLOB_API = "https://clob.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"


# --- Aideurs Base de Données ---
def init_db():
    """Initialise la base SQLite pour stocker les abonnements."""
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                chat_id TEXT,
                token_id TEXT,
                PRIMARY KEY (chat_id, token_id)
            )
        """)

def add_subscription(chat_id: int, token_id: str):
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT OR IGNORE INTO subscriptions(chat_id, token_id) VALUES (?, ?)",
            (str(chat_id), token_id)
        )

def remove_subscription(chat_id: int, token_id: str):
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "DELETE FROM subscriptions WHERE chat_id=? AND token_id=?",
            (str(chat_id), token_id)
        )

def list_tokens():
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute("SELECT DISTINCT token_id FROM subscriptions").fetchall()
        return [r[0] for r in rows]

def list_subscribers_for_token(token_id: str):
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            "SELECT chat_id FROM subscriptions WHERE token_id=?", 
            (token_id,)
        ).fetchall()
        return [r[0] for r in rows]


# --- Logique API Polymarket ---
def parse_json_field(field):
    """Décode proprement les champs (Yes/No) sans les caractères [ ou \"."""
    if isinstance(field, str):
        try:
            return json.loads(field)
        except (json.JSONDecodeError, TypeError):
            return []
    return field if isinstance(field, list) else []

def fetch_market_data(token_id: str):
    """Récupère les prix et volumes via l'API CLOB."""
    try:
        # Récupération du prix Mid
        mid_resp = requests.get(f"{CLOB_API}/midpoint", params={"token_id": token_id}, timeout=10)
        mid_price = mid_resp.json().get("mid") if mid_resp.status_code == 200 else "N/A"

        # Prix Achat (Bid) et Vente (Ask) précis
        bid_resp = requests.get(f"{CLOB_API}/price", params={"token_id": token_id, "side": "buy"}, timeout=10)
        best_bid = float(bid_resp.json().get("price", 0)) if bid_resp.status_code == 200 else None

        ask_resp = requests.get(f"{CLOB_API}/price", params={"token_id": token_id, "side": "sell"}, timeout=10)
        best_ask = float(ask_resp.json().get("price", 0)) if ask_resp.status_code == 200 else None

        # Profondeur (Size) via /book
        book_resp = requests.get(f"{CLOB_API}/book", params={"token_id": token_id}, timeout=10)
        book_data = book_resp.json()
        bid_size = float(book_data.get("bids", [{}])[0].get("size", 0)) if book_data.get("bids") else 0
        ask_size = float(book_data.get("asks", [{}])[0].get("size", 0)) if book_data.get("asks") else 0

        spread = round(abs(best_ask - best_bid), 4) if (best_bid and best_ask) else None

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
        logger.error(f"Erreur API pour {token_id}: {e}")
        return None

def get_market_info_gamma(token_id: str):
    """Récupère le contexte du marché via Gamma."""
    try:
        resp = requests.get(f"{GAMMA_API}/markets", params={"active": "true", "limit": 100}, timeout=10)
        markets = resp.json()
        for m in markets:
            tokens = parse_json_field(m.get("clobTokenIds"))
            if token_id in tokens:
                idx = tokens.index(token_id)
                outcomes = parse_json_field(m.get("outcomes"))
                return {
                    "question": m.get("question", "N/A"),
                    "outcome": outcomes[idx] if idx < len(outcomes) else "N/A",
                    "slug": m.get("slug", "")
                }
    except:
        return None
    return None


# --- Formatage ---
def format_market_message(info: dict, m_info: dict = None):
    if not info or info.get('best_bid') is None:
        return "❌ Données indisponibles."

    bid_c = info['best_bid'] * 100
    ask_c = info['best_ask'] * 100
    
    lines = [
        "📊 **Mise à jour Polymarket**",
        f"❓ `{m_info['question'] if m_info else 'Marché inconnu'}`",
        f"📍 Pari : **{m_info['outcome'] if m_info else 'N/A'}**",
        "",
        f"💰 Prix Mid : **{info['mid_price']}**",
        f"🟢 **BID (Achat) : {bid_c:.1f}¢** (taille: {info['bid_size']:.0f})",
        f"🔴 **ASK (Vente) : {ask_c:.1f}¢** (taille: {info['ask_size']:.0f})",
        f"📏 Spread : {info['spread']*100:.1f}¢" if info['spread'] else "",
        "",
        f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
    ]
    return "\n".join(filter(None, lines))


# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 **Bienvenue sur le bot Polymarket!**\n\n"
        "• `/search <terme>` - Chercher des marchés\n"
        "• `/subscribe <id>` - S'abonner aux prix\n"
        "• `/unsubscribe <id>` - Se désabonner\n"
        "• `/status` - Voir vos abonnements\n"
        "• `/check <id>` - Vérifier un prix\n"
        "• `/test` - Forcer la mise à jour immédiate",
        parse_mode='Markdown'
    )

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Usage : `/search trump`")
        return
    try:
        resp = requests.get(f"{GAMMA_API}/events", params={"q": query, "active": "true"}, timeout=10)
        events = resp.json()
        if not events:
            await update.message.reply_text("❌ Aucun résultat.")
            return
        msg = f"🔍 **Résultats pour '{query}' :**\n\n"
        for event in events[:5]:
            msg += f"📅 **{event['title']}**\n"
            for m in event.get('markets', []):
                tokens = parse_json_field(m.get('clobTokenIds'))
                outcomes = parse_json_field(m.get('outcomes'))
                if tokens:
                    msg += f"  ❓ {m['question'][:50]}...\n"
                    for i, t_id in enumerate(tokens):
                        out_name = outcomes[i] if i < len(outcomes) else "?"
                        msg += f"    • {out_name}: `/subscribe {t_id}`\n"
            msg += "\n"
        await update.message.reply_text(msg, parse_mode='Markdown')
    except:
        await update.message.reply_text("❌ Erreur de recherche.")

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    t_id = context.args[0]
    add_subscription(update.effective_chat.id, t_id)
    info = fetch_market_data(t_id)
    m_info = get_market_info_gamma(t_id)
    await update.message.reply_text(f"✅ Abonné !\n\n{format_market_message(info, m_info)}", parse_mode='Markdown')

async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    t_id = context.args[0]
    remove_subscription(update.effective_chat.id, t_id)
    await update.message.reply_text(f"✅ Désabonné de `{t_id[:10]}...`")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute("SELECT token_id FROM subscriptions WHERE chat_id=?", (str(update.effective_chat.id),)).fetchall()
    if not rows:
        await update.message.reply_text("Aucun abonnement.")
    else:
        msg = "📋 **Vos abonnements :**\n\n"
        for (t_id,) in rows:
            m_info = get_market_info_gamma(t_id)
            name = f"{m_info['outcome']} - {m_info['question'][:30]}..." if m_info else t_id[:15]
            msg += f"• `{t_id}`\n({name})\n"
        await update.message.reply_text(msg, parse_mode='Markdown')

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    t_id = context.args[0]
    info = fetch_market_data(t_id)
    m_info = get_market_info_gamma(t_id)
    await update.message.reply_text(format_market_message(info, m_info), parse_mode='Markdown')

async def test_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Test : Envoi manuel des mises à jour...")
    await job_send_updates(context.application)
    await update.message.reply_text("✅ Test terminé.")


# --- Jobs ---
async def job_send_updates(application):
    tokens = list_tokens()
    for t_id in tokens:
        info = fetch_market_data(t_id)
        m_info = get_market_info_gamma(t_id)
        msg = format_market_message(info, m_info)
        for chat_id in list_subscribers_for_token(t_id):
            try: await application.bot.send_message(chat_id=int(chat_id), text=msg, parse_mode='Markdown')
            except: continue

async def post_init(application):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(job_send_updates, 'interval', hours=1, args=[application])
    scheduler.start()


# --- Main ---
def main():
    init_db()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("check", check))
    app.add_handler(CommandHandler("search", search))
    app.add_handler(CommandHandler("test", test_job))
    
    logger.info("🤖 Bot Polymarket démarré avec tous les handlers")
    app.run_polling()

if __name__ == "__main__":
    main()