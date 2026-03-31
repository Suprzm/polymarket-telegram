import sqlite3
import logging

logger = logging.getLogger(__name__)

DB_PATH = "data/subscriptions.db"


def init_db():
    """Initialize database with all required tables"""
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
    logger.info("✅ Database initialized")


def add_subscription(chat_id: int, token_id: str):
    """Add a subscription"""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO subscriptions(chat_id, token_id) VALUES (?, ?)",
                (str(chat_id), token_id))
    con.commit()
    con.close()


def remove_subscription(chat_id: int, token_id: str):
    """Remove a subscription"""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("DELETE FROM subscriptions WHERE chat_id=? AND token_id=?",
                (str(chat_id), token_id))
    con.commit()
    con.close()


def list_subscribers_for_token(token_id: str):
    """Get all subscribers for a token"""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT chat_id FROM subscriptions WHERE token_id=?", (token_id,))
    rows = [r[0] for r in cur.fetchall()]
    con.close()
    return rows


def list_tokens():
    """Get all subscribed tokens"""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT DISTINCT token_id FROM subscriptions")
    rows = [r[0] for r in cur.fetchall()]
    con.close()
    return rows


def get_user_subscriptions(chat_id: int):
    """Get all subscriptions for a user"""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT token_id FROM subscriptions WHERE chat_id=?", (str(chat_id),))
    rows = [r[0] for r in cur.fetchall()]
    con.close()
    return rows


def delete_all_user_subscriptions(chat_id: int):
    """Delete all subscriptions for a user"""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM subscriptions WHERE chat_id=?", (str(chat_id),))
    count = cur.fetchone()[0]
    cur.execute("DELETE FROM subscriptions WHERE chat_id=?", (str(chat_id),))
    con.commit()
    con.close()
    return count


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