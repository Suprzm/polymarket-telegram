from datetime import datetime


def escape_markdown(text: str) -> str:
    """Escape special characters for Markdown V2"""
    if text is None:
        return "N/A"
    
    text = str(text)
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


def format_market_message(info: dict, market_info: dict = None):
    """Format market data as Telegram message"""
    if not info:
        return "❌ Error: unable to fetch market data\\."

    lines = ["📊 *Polymarket Update*", ""]
    
    # Always show market info if available
    if market_info:
        question = escape_markdown(market_info.get('question', 'N/A'))
        outcome = escape_markdown(market_info.get('outcome', 'N/A'))
        lines.extend([
            f"*Market:* {question}",
            f"*Outcome:* {outcome}",
            ""
        ])
    else:
        lines.append("*Market:* Unknown")
        lines.append("")
    
    token_short = escape_markdown(str(info.get('token_id', 'N/A'))[:20] + "...")
    mid = escape_markdown(info.get('mid_price') if info.get('mid_price') is not None else 'N/A')
    bid = escape_markdown(info.get('best_bid') if info.get('best_bid') is not None else 'N/A')
    ask = escape_markdown(info.get('best_ask') if info.get('best_ask') is not None else 'N/A')
    bid_size = escape_markdown(info.get('bid_size') if info.get('bid_size') is not None else 'N/A')
    ask_size = escape_markdown(info.get('ask_size') if info.get('ask_size') is not None else 'N/A')
    
    lines.extend([
        f"🔑 *Token ID:* `{token_short}`",
        "",
        f"💰 *Mid price:* {mid}",
        f"📈 *Best bid:* {bid} \\(size: {bid_size}\\)",
        f"📉 *Best ask:* {ask} \\(size: {ask_size}\\)",
    ])
    
    if info.get('spread') is not None:
        spread = escape_markdown(info.get('spread'))
        lines.append(f"📏 *Spread:* {spread}%")
    
    timestamp_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    timestamp = escape_markdown(timestamp_str)
    lines.extend([
        "",
        f"⏰ {timestamp} UTC"
    ])
    
    return "\n".join(lines)