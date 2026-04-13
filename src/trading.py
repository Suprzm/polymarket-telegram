import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType
from py_clob_client.constants import POLYGON
from py_clob_client.order_builder.constants import BUY, SELL

from .poly_api import fetch_market_data

load_dotenv()
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────

@dataclass
class MMConfig:
    """Market making configuration for a single token."""
    token_id: str
    spread: float = 0.04        # total spread, bid = mid - spread/2, ask = mid + spread/2
    size: float = 5.0           # $ size per order
    mid_threshold: float = 0.02 # cancel & replace if mid moves by this amount
    poll_interval: int = 30     # seconds between checks


@dataclass
class MMState:
    """Runtime state for a running market maker."""
    config: MMConfig
    mid_ref: Optional[float] = None       # mid price when orders were last placed
    bid_order_id: Optional[str] = None    # current live BUY order id
    ask_order_id: Optional[str] = None    # current live SELL order id
    bid_size_matched: float = 0.0         # matched size on BUY order (fill detection)
    ask_size_matched: float = 0.0         # matched size on SELL order (fill detection)
    task: Optional[asyncio.Task] = None   # background asyncio task


# ──────────────────────────────────────────────
# Client factory
# ──────────────────────────────────────────────

def _build_client() -> ClobClient:
    creds = ApiCreds(
        api_key=os.getenv("POLY_API_KEY"),
        api_secret=os.getenv("POLY_API_SECRET"),
        api_passphrase=os.getenv("POLY_API_PASSPHRASE"),
    )
    return ClobClient(
        host="https://clob.polymarket.com",
        key=os.getenv("POLY_PRIVATE_KEY"),
        chain_id=POLYGON,
        creds=creds,
        signature_type=0,           # EOA (MetaMask)
        funder=os.getenv("POLY_FUNDER_ADDRESS"),
    )


# ──────────────────────────────────────────────
# Order helpers
# ──────────────────────────────────────────────

def _place_order(client: ClobClient, token_id: str, side: str, price: float, size: float) -> Optional[str]:
    """
    Place a GTC limit order. Returns order_id or None on failure.
    Price is rounded to 2 decimals (Polymarket tick size 0.01).
    """
    try:
        price = round(price, 2)
        # Clamp price to valid range
        price = max(0.01, min(0.99, price))

        order_args = OrderArgs(
            token_id=token_id,
            price=price,
            size=size,
            side=side,
        )
        resp = client.create_and_post_order(order_args)
        order_id = resp.get("orderID") or resp.get("order_id")
        logger.info(f"✅ Order placed: {side} {size} @ {price} → id={order_id}")
        return order_id
    except Exception as e:
        logger.error(f"❌ Failed to place {side} order: {e}")
        return None


def _cancel_order(client: ClobClient, order_id: str):
    """Cancel a single order, ignoring errors (already filled/cancelled)."""
    try:
        client.cancel(order_id=order_id)
        logger.info(f"🗑️ Cancelled order {order_id}")
    except Exception as e:
        logger.warning(f"⚠️ Could not cancel order {order_id}: {e}")


def _get_order_info(client: ClobClient, order_id: str) -> Optional[dict]:
    """Fetch current state of an order. Returns None if not found."""
    try:
        return client.get_order(order_id)
    except Exception:
        return None


# ──────────────────────────────────────────────
# Fill detection
# ──────────────────────────────────────────────

def _detect_fill(client: ClobClient, state: MMState) -> tuple[bool, bool]:
    """
    Check if bid or ask orders have been (partially) filled.
    Returns (bid_filled, ask_filled).
    """
    bid_filled = False
    ask_filled = False

    if state.bid_order_id:
        info = _get_order_info(client, state.bid_order_id)
        if info is None:
            # Order gone → fully filled or cancelled externally
            bid_filled = True
        else:
            matched = float(info.get("size_matched", 0))
            if matched > state.bid_size_matched:
                bid_filled = True
                state.bid_size_matched = matched

    if state.ask_order_id:
        info = _get_order_info(client, state.ask_order_id)
        if info is None:
            ask_filled = True
        else:
            matched = float(info.get("size_matched", 0))
            if matched > state.ask_size_matched:
                ask_filled = True
                state.ask_size_matched = matched

    return bid_filled, ask_filled


# ──────────────────────────────────────────────
# Core MM logic
# ──────────────────────────────────────────────

def _cancel_all(client: ClobClient, state: MMState):
    """Cancel both active orders and reset state."""
    if state.bid_order_id:
        _cancel_order(client, state.bid_order_id)
        state.bid_order_id = None
    if state.ask_order_id:
        _cancel_order(client, state.ask_order_id)
        state.ask_order_id = None
    state.bid_size_matched = 0.0
    state.ask_size_matched = 0.0
    state.mid_ref = None


def _place_quotes(client: ClobClient, state: MMState, mid: float, notify_cb=None):
    """Cancel existing orders and place fresh bid/ask around mid."""
    cfg = state.config
    half = cfg.spread / 2
    bid_price = mid - half
    ask_price = mid + half

    _cancel_all(client, state)

    state.bid_order_id = _place_order(client, cfg.token_id, BUY, bid_price, cfg.size)
    state.ask_order_id = _place_order(client, cfg.token_id, SELL, ask_price, cfg.size)
    state.mid_ref = mid

    logger.info(f"📊 Quotes placed | mid={mid:.3f} bid={bid_price:.3f} ask={ask_price:.3f}")

    if notify_cb:
        notify_cb(
            f"📊 <b>MM quotes placed</b>\n"
            f"Token: <code>{cfg.token_id[:20]}...</code>\n"
            f"BUY  @ {bid_price:.3f} | SELL @ {ask_price:.3f}\n"
            f"Size: ${cfg.size} each"
        )


async def _mm_loop(state: MMState, notify_cb=None):
    """
    Main market making loop for a single token.
    Runs until cancelled.
    """
    cfg = state.config
    client = _build_client()

    logger.info(f"🚀 MM started for token {cfg.token_id[:20]}...")

    try:
        while True:
            # 1. Fetch current mid price
            market_data = fetch_market_data(cfg.token_id)
            if not market_data or market_data.get("mid_price") is None:
                logger.warning(f"⚠️ Could not fetch mid price, skipping cycle")
                await asyncio.sleep(cfg.poll_interval)
                continue

            mid = float(market_data["mid_price"])

            # 2. First cycle → place quotes immediately
            if state.mid_ref is None:
                _place_quotes(client, state, mid, notify_cb)
                await asyncio.sleep(cfg.poll_interval)
                continue

            # 3. Check for fills
            bid_filled, ask_filled = _detect_fill(client, state)
            if bid_filled or ask_filled:
                filled_side = []
                if bid_filled:
                    filled_side.append("BUY")
                if ask_filled:
                    filled_side.append("SELL")

                logger.info(f"🎯 Fill detected on {filled_side} → replacing quotes")

                if notify_cb:
                    notify_cb(
                        f"🎯 <b>Fill detected!</b>\n"
                        f"Side(s): {', '.join(filled_side)}\n"
                        f"Token: <code>{cfg.token_id[:20]}...</code>\n"
                        f"Replacing quotes..."
                    )
                _place_quotes(client, state, mid, notify_cb)
                await asyncio.sleep(cfg.poll_interval)
                continue

            # 4. Check mid price movement
            mid_move = abs(mid - state.mid_ref)
            if mid_move >= cfg.mid_threshold:
                logger.info(f"📈 Mid moved {mid_move:.3f} ≥ threshold {cfg.mid_threshold} → replacing quotes")

                if notify_cb:
                    notify_cb(
                        f"📈 <b>Mid price moved</b>\n"
                        f"Token: <code>{cfg.token_id[:20]}...</code>\n"
                        f"Old mid: {state.mid_ref:.3f} → New mid: {mid:.3f}\n"
                        f"Replacing quotes..."
                    )
                _place_quotes(client, state, mid, notify_cb)
            else:
                logger.info(f"😴 No action | mid={mid:.3f} move={mid_move:.3f} < threshold={cfg.mid_threshold}")

            await asyncio.sleep(cfg.poll_interval)

    except asyncio.CancelledError:
        logger.info(f"🛑 MM loop cancelled for {cfg.token_id[:20]}... — cleaning up orders")
        _cancel_all(client, state)
        if notify_cb:
            notify_cb(f"🛑 <b>MM stopped</b> — all orders cancelled\nToken: <code>{cfg.token_id[:20]}...</code>")
        raise


# ──────────────────────────────────────────────
# Public API (used by Telegram handlers)
# ──────────────────────────────────────────────

# Active market makers: token_id → MMState
_active_mm: dict[str, MMState] = {}


def start_mm(token_id: str, config: Optional[MMConfig] = None, notify_cb=None) -> bool:
    """
    Start market making on a token.
    Returns False if already running.
    """
    if token_id in _active_mm:
        logger.warning(f"MM already running for {token_id[:20]}...")
        return False

    cfg = config or MMConfig(token_id=token_id)
    state = MMState(config=cfg)

    task = asyncio.create_task(_mm_loop(state, notify_cb))
    state.task = task
    _active_mm[token_id] = state

    logger.info(f"✅ MM started for {token_id[:20]}...")
    return True


def stop_mm(token_id: str) -> bool:
    """
    Stop market making on a token and cancel its orders.
    Returns False if not running.
    """
    state = _active_mm.pop(token_id, None)
    if not state or not state.task:
        return False

    state.task.cancel()
    logger.info(f"🛑 MM stop requested for {token_id[:20]}...")
    return True


def stop_all_mm() -> int:
    """Stop all running market makers. Returns count stopped."""
    tokens = list(_active_mm.keys())
    for token_id in tokens:
        stop_mm(token_id)
    return len(tokens)


def list_active_mm() -> list[dict]:
    """Return info about all active market makers."""
    result = []
    for token_id, state in _active_mm.items():
        cfg = state.config
        result.append({
            "token_id": token_id,
            "mid_ref": state.mid_ref,
            "bid_order_id": state.bid_order_id,
            "ask_order_id": state.ask_order_id,
            "spread": cfg.spread,
            "size": cfg.size,
            "mid_threshold": cfg.mid_threshold,
        })
    return result