import sqlite3

conn = sqlite3.connect("polymarket.db")
cur = conn.cursor()

# Market table (fixed infos)
cur.execute("""
CREATE TABLE IF NOT EXISTS markets (
    market_id TEXT PRIMARY KEY,
    question TEXT,
    outcomes TEXT,
    raw_json TEXT
)
""")

# Snapshots table (variable infos, hourly snapshots)
cur.execute("""
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    best_bid REAL,
    best_ask REAL,
    mid REAL,
    volume24h REAL,
    liquidity REAL,
    orderbook TEXT,
    raw_json TEXT,
    FOREIGN KEY(market_id) REFERENCES markets(market_id)
)
""")

conn.commit()
conn.close()

print("Database initialized.")