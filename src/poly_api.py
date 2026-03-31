import requests
import json
import logging

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"
logger = logging.getLogger(__name__)

def fetch_market_data(token_id):
    """Récupère les prix via Gamma et le carnet via CLOB"""
    try:
        # 1. Gamma pour le prix de référence
        resp = requests.get(f"{GAMMA_API}/markets", params={"limit": 100}, timeout=10)
        markets = resp.json()
        
        for m in markets:
            clob_ids = json.loads(m['clobTokenIds']) if isinstance(m['clobTokenIds'], str) else m['clobTokenIds']
            if token_id in clob_ids:
                idx = clob_ids.index(token_id)
                prices = json.loads(m['outcomePrices']) if isinstance(m['outcomePrices'], str) else m['outcomePrices']
                price = float(prices[idx]) if idx < len(prices) else None
                
                # 2. CLOB pour le spread réel
                book_resp = requests.get(f"{CLOB_API}/book", params={"token_id": token_id}, timeout=5)
                bids = book_resp.json().get("bids", [])
                asks = book_resp.json().get("asks", [])
                
                best_bid = float(bids[-1]["price"]) if bids else None
                best_ask = float(asks[-1]["price"]) if asks else None
                
                return {
                    "token_id": token_id, "mid_price": price,
                    "best_bid": best_bid, "best_ask": best_ask,
                    "bid_size": float(bids[-1]["size"]) if bids else None,
                    "ask_size": float(asks[-1]["size"]) if asks else None,
                    "spread": round((best_ask - best_bid) * 100, 2) if (best_bid and best_ask) else None
                }
    except Exception as e:
        logger.error(f"API Error: {e}")
    return None

def public_search(query):
    try:
        resp = requests.get(f"{GAMMA_API}/public-search", params={"q": query}, timeout=10)
        return resp.json().get("events", [])
    except: return []