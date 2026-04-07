import logging
import requests
from datetime import datetime
from src.poly_api import DATA_API

logger = logging.getLogger(__name__)

class PolyWallet:
    def __init__(self, wallet_address: str):
        self.address = wallet_address.lower()

    def get_positions(self) -> list:
        """
        Fetch open positions via Data API.
        Returns list of Position objects with P&L already computed by the API.
        """
        try:
            resp = requests.get(
                f"{DATA_API}/positions",
                params={
                    "user": self.address,
                    "sizeThreshold": 0.01,
                    "sortBy": "CASHPNL",
                    "sortDirection": "DESC",
                    "limit": 50,
                },
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []

    def get_trades(self, limit: int = 5) -> list:
        """
        Fetch recent trades via Data API.
        Note: takerOnly=False to get both maker and taker trades.
        """
        try:
            resp = requests.get(
                f"{DATA_API}/trades",
                params={
                    "user": self.address,
                    "takerOnly": False,
                    "limit": limit,
                },
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Error fetching trades: {e}")
            return []

    def get_total_value(self) -> float:
        """
        Fetch total current value of all open positions.
        Returns float (USDC) or None on error.
        """
        try:
            resp = requests.get(
                f"{DATA_API}/value",
                params={"user": self.address},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            # Returns list: [{"user": "0x...", "value": 123.45}]
            if data and isinstance(data, list):
                return float(data[0].get("value", 0.0))
            return 0.0
        except Exception as e:
            logger.error(f"Error fetching total value: {e}")
            return None

    def get_summary(self) -> dict:
        """
        Aggregate all wallet data in one call.
        Returns dict with positions, trades, total_value, global_pnl.
        """
        positions = self.get_positions()
        trades = self.get_trades(limit=5)
        total_value = self.get_total_value()

        # Global P&L = sum of cashPnl across all positions (already computed by API)
        global_pnl = sum(float(p.get("cashPnl", 0)) for p in positions)

        return {
            "address": self.address,
            "positions": positions,
            "trades": trades,
            "total_value": total_value,
            "global_pnl": global_pnl,
        }


def format_wallet_message(summary: dict) -> str:
    """
    Format wallet summary as Telegram HTML message.
    Uses HTML parse_mode (simpler than MarkdownV2 for dynamic content).
    """
    address = summary["address"]
    positions = summary["positions"]
    trades = summary["trades"]
    total_value = summary.get("total_value") or 0.0
    global_pnl = summary.get("global_pnl", 0.0)

    short_addr = f"{address[:6]}...{address[-4:]}"
    pnl_icon = "💰" if global_pnl >= 0 else "💸"
    pnl_sign = "+" if global_pnl >= 0 else ""

    lines = [
        f"💳 <b>Polymarket Portfolio</b>",
        f"👤 Wallet: <code>{short_addr}</code>",
        f"💵 Total value: <b>${total_value:.2f}</b>",
        f"{pnl_icon} P&amp;L global: <b>{pnl_sign}{global_pnl:.2f} USDC</b>",
        "",
        "<b>📍 Open positions :</b>",
    ]

    if not positions:
        lines.append("<i>No open position.</i>")
    else:
        for p in positions[:10]:  # Max 10 pour pas exploser le message
            size = float(p.get("size", 0))
            cur_price = float(p.get("curPrice", 0))
            avg_price = float(p.get("avgPrice", 0))
            cash_pnl = float(p.get("cashPnl", 0))
            pct_pnl = float(p.get("percentPnl", 0))
            title = p.get("title", "Unknown")[:45]
            outcome = p.get("outcome", "?")

            color = "🟢" if cash_pnl >= 0 else "🔴"
            pnl_sign = "+" if cash_pnl >= 0 else ""

            lines.append(
                f"{color} <b>{outcome}</b> — {title}\n"
                f"   {size:.1f} tokens @ {avg_price:.3f} → {cur_price:.3f} | "
                f"P&amp;L: <b>{pnl_sign}{cash_pnl:.2f}$ ({pct_pnl:+.1f}%)</b>"
            )

    lines.append("")
    lines.append("<b>🕒 Last trades :</b>")

    if not trades:
        lines.append("<i>No recent trade.</i>")
    else:
        for t in trades:
            side = t.get("side", "?")
            size = float(t.get("size", 0))
            price = float(t.get("price", 0))
            outcome = t.get("outcome", "?")
            title = t.get("title", "Unknown")[:35]
            ts = t.get("timestamp")
            date_str = (
                datetime.utcfromtimestamp(ts).strftime("%d/%m %H:%M")
                if ts else "?"
            )

            side_icon = "🔵" if side == "BUY" else "🟠"
            lines.append(
                f"{side_icon} <b>{side}</b> {size:.1f} @ {price:.3f} "
                f"| {outcome} — {title} <i>({date_str})</i>"
            )

    lines.append("")
    lines.append(f"<i>⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC</i>")

    return "\n".join(lines)