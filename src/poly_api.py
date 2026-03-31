import requests
import json
import logging

logger = logging.getLogger(__name__)

CLOB_API = "https://clob.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"


def fetch_market_data(token_id: str):
    """
    Fetch market data for a token via Polymarket's Gamma API.
    Falls back to CLOB if not found in Gamma.
    """
    try:
        token_id = str(token_id).strip().rstrip('.')
        logger.info(f"Fetching data for token: {token_id[:20]}...")
        
        # Try Gamma API first
        url = f"{GAMMA_API}/markets"
        params = {"limit": 100}
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        markets = resp.json()
        
        # Search for token in first batch
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
                
                # Try to get CLOB data
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
                    pass
                
                spread = None
                if best_bid and best_ask:
                    spread = round((best_ask - best_bid) * 100, 2)
                
                return {
                    "token_id": token_id,
                    "mid_price": price,
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "bid_size": bid_size,
                    "ask_size": ask_size,
                    "spread": spread,
                }
        
        # Search more markets
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
        
        logger.error(f"Token {token_id[:20]}... not found in any markets")
        
        # Last resort: CLOB fallback
        logger.info(f"Attempting direct CLOB lookup as fallback...")
        try:
            mid_url = f"{CLOB_API}/midpoint"
            mid_params = {"token_id": token_id}
            mid_resp = requests.get(mid_url, params=mid_params, timeout=10)
            
            if mid_resp.status_code == 200:
                mid_data = mid_resp.json()
                mid_price = mid_data.get("mid")
                
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
        logger.error(f"HTTP Error for token {token_id[:20]}...: {e.response.status_code}")
        return None
    except Exception as e:
        logger.exception(f"Error in fetch_market_data for token {token_id[:20]}...: {e}")
        return None


def get_market_info_from_gamma(token_id: str):
    """
    Fetch market info from Gamma API.
    Priority: permanent DB > search cache > Gamma API
    """
    from .database import get_market_metadata, get_from_search_cache, save_market_metadata
    
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
    
    # 3. Search Gamma API
    logger.info(f"🔍 Searching Gamma API for token {token_id[:20]}...")
    
    try:
        url = f"{GAMMA_API}/markets"
        
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
                        "event_title": market.get("question", "N/A")
                    }
                    
                    # Save to permanent DB
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