import logging
import requests
import os
from datetime import datetime
from web3 import Web3
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

# Constants for Polymarket Data API and Polygon Network
DATA_API = "https://data-api.polymarket.com"
USDC_E_CONTRACT = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
USDC_E_ABI = [{"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"}]
POLYGON_RPCS = [
    "https://polygon.llamarpc.com",
    "https://rpc.ankr.com/polygon",
    "https://polygon-bor-rpc.publicnode.com",
]

def _get_web3() -> Web3 | None:
    """
    Get a connected Web3 instance by trying multiple public Polygon RPCs.
    """
    for rpc in POLYGON_RPCS:
        try:
            w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 5}))
            if w3.is_connected():
                return w3
        except Exception as e:
            logger.debug(f"RPC {rpc} failed: {e}")
            continue
    logger.error("❌ No Polygon RPC available")
    return None


class PolyWallet:
    def __init__(self, wallet_address: str):
        """
        Initialize the wallet and ensure the address is in Checksum format.
        """
        self.address = Web3.to_checksum_address(wallet_address)

    def get_positions(self) -> list:
        """
        Fetch open positions via Polymarket Data API.
        """
        try:
            resp = requests.get(
                f"{DATA_API}/positions",
                params={
                    "user": self.address.lower(), # Data API strictly requires lowercase
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
        Fetch recent trades via Polymarket Data API.
        """
        try:
            resp = requests.get(
                f"{DATA_API}/trades",
                params={
                    "user": self.address.lower(),
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

    def get_cash_balance(self) -> float | None:
        """
        Fetch available USDC.e balance directly on-chain using Web3.
        """
        try:
            w3 = _get_web3()
            if not w3:
                return None
            
            contract = w3.eth.contract(
                address=Web3.to_checksum_address(USDC_E_CONTRACT),
                abi=USDC_E_ABI
            )
            
            # Call the smart contract function
            balance_raw = contract.functions.balanceOf(self.address).call()
            
            # USDC.e uses 6 decimal places / 6 décimales pour l'USDC.e
            return float(balance_raw) / 1e6 
        except Exception as e:
            logger.error(f"Error fetching on-chain cash balance: {e}")
            return None

    def get_summary(self) -> dict:
        """
        Aggregate all wallet data: Positions, Trades, and On-chain Balance.
        Regroupe toutes les données : positions, trades et solde on-chain.
        """
        positions = self.get_positions()
        trades = self.get_trades(limit=5)
        cash_balance = self.get_cash_balance()

        # Global P&L: sum of cashPnl across all positions
        global_pnl = sum(float(p.get("cashPnl", 0)) for p in positions)
        
        # Current Value: sum of the market value of all open positions
        positions_value = sum(float(p.get("currentValue", 0)) for p in positions)

        return {
            "address": self.address,
            "positions": positions,
            "trades": trades,
            "cash_balance": cash_balance,
            "positions_value": positions_value,
            "global_pnl": global_pnl,
        }


def format_wallet_message(summary: dict) -> str:
    """
    Format the wallet summary into a clean Telegram HTML message.
    Formate le résumé du portefeuille en message HTML pour Telegram.
    """
    address = summary["address"]
    positions = summary["positions"]
    trades = summary["trades"]
    cash_balance = summary.get("cash_balance") or 0.0
    positions_value = summary.get("positions_value", 0.0)
    global_pnl = summary.get("global_pnl", 0.0)
    total = cash_balance + positions_value

    short_addr = f"{address[:6]}...{address[-4:]}"
    pnl_icon = "💰" if global_pnl >= 0 else "💸"

    lines = [
        f"💳 <b>Polymarket Portfolio</b>",
        f"👤 Wallet: <code>{short_addr}</code>",
        "",
        f"💵 Cash dispo: <b>${cash_balance:.2f} USDC.e</b>",
        f"📊 Valeur positions: <b>${positions_value:.2f}</b>",
        f"🏦 Total: <b>${total:.2f}</b>",
        f"{pnl_icon} P&amp;L global: <b>{global_pnl:+.2f} USDC</b>",
        "",
        "<b>📍 Open positions:</b>",
    ]

    if not positions:
        lines.append("<i>No open position.</i>")
    else:
        # Display top 10 positions only to avoid long messages
        for p in positions[:10]:
            size = float(p.get("size", 0))
            cur_price = float(p.get("curPrice", 0))
            avg_price = float(p.get("avgPrice", 0))
            cash_pnl = float(p.get("cashPnl", 0))
            pct_pnl = float(p.get("percentPnl", 0))
            title = p.get("title", "Unknown")[:45]
            outcome = p.get("outcome", "?")

            color = "🟢" if cash_pnl >= 0 else "🔴"
            lines.append(
                f"{color} <b>{outcome}</b> — {title}\n"
                f"   {size:.1f} tokens @ {avg_price:.3f} → {cur_price:.3f} | "
                f"P&amp;L: <b>{cash_pnl:+.2f}$ ({pct_pnl:+.1f}%)</b>"
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
            
            # Formatting the timestamp into a readable date
            try:
                date_str = datetime.utcfromtimestamp(int(ts)).strftime("%d/%m %H:%M") if ts else "?"
            except:
                date_str = "?"
                
            side_icon = "🔵" if side == "BUY" else "🟠"
            lines.append(
                f"{side_icon} <b>{side}</b> {size:.1f} @ {price:.3f} "
                f"| {outcome} — {title} <i>({date_str})</i>"
            )

    lines.append("")
    lines.append(f"<i>⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC</i>")

    return "\n".join(lines)