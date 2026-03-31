import sqlite3
import logging

DB_PATH = "data/subscriptions.db"
logger = logging.getLogger(__name__)

def query_db(query, args=(), one=False):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(query, args)
        rv = cur.fetchall()
        conn.commit()
        return (rv[0] if rv else None) if one else rv

def init_db():
    query_db("""CREATE TABLE IF NOT EXISTS subscriptions 
                (chat_id TEXT, token_id TEXT, PRIMARY KEY (chat_id, token_id))""")
    
    query_db("""CREATE TABLE IF NOT EXISTS market_metadata (
                token_id TEXT PRIMARY KEY, question TEXT, outcome TEXT, 
                slug TEXT, event_title TEXT, last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    
    query_db("""CREATE TABLE IF NOT EXISTS search_cache (
                token_id TEXT PRIMARY KEY, question TEXT, outcome TEXT, 
                slug TEXT, event_title TEXT, cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

def add_subscription(chat_id, token_id):
    query_db("INSERT OR IGNORE INTO subscriptions(chat_id, token_id) VALUES (?, ?)", (str(chat_id), token_id))

def remove_subscription(chat_id, token_id):
    query_db("DELETE FROM subscriptions WHERE chat_id=? AND token_id=?", (str(chat_id), token_id))

def list_tokens():
    return [r[0] for r in query_db("SELECT DISTINCT token_id FROM subscriptions")]

def list_subscribers(token_id):
    return [r[0] for r in query_db("SELECT chat_id FROM subscriptions WHERE token_id=?", (token_id,))]

def save_metadata(token_id, q, out, slug, title, table="market_metadata"):
    query_db(f"INSERT OR REPLACE INTO {table} (token_id, question, outcome, slug, event_title) VALUES (?,?,?,?,?)",
             (token_id, q, out, slug, title))

def get_metadata(token_id):
    row = query_db("SELECT question, outcome, slug, event_title FROM market_metadata WHERE token_id = ?", (token_id,), one=True)
    if not row:
        row = query_db("SELECT question, outcome, slug, event_title FROM search_cache WHERE token_id = ?", (token_id,), one=True)
    return {"question": row[0], "outcome": row[1], "slug": row[2], "event_title": row[3]} if row else None

def clear_search_cache():
    query_db("DELETE FROM search_cache")