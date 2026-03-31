import html
from datetime import datetime

def format_market_message(info, m_info):
    if not info: return "❌ Erreur de données."
    
    q = html.escape(m_info.get('question', 'Marché inconnu')) if m_info else "Inconnu"
    out = html.escape(m_info.get('outcome', 'N/A')) if m_info else "N/A"
    
    msg = [
        f"📊 <b>Polymarket Update</b>",
        f"❓ {q}",
        f"📍 Pari : <b>{out}</b>",
        "",
        f"💰 Prix Mid : <code>{info.get('mid_price', 'N/A')}</code>",
        f"🟢 BID : <code>{info.get('best_bid', 'N/A')}</code> (vol: {info.get('bid_size', 'N/A')})",
        f"🔴 ASK : <code>{info.get('best_ask', 'N/A')}</code> (vol: {info.get('ask_size', 'N/A')})",
    ]
    
    if info.get('spread'):
        msg.append(f"📏 Spread : {info['spread']}%")
        
    msg.append(f"\n⏰ {datetime.utcnow().strftime('%H:%M:%S')} UTC")
    return "\n".join(msg)