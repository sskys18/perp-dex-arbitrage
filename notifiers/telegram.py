"""Telegram notification handler"""

import os
from telegram import Bot
from models import Signal


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


async def send_telegram_init(exchanges: list[str], symbols: list[str]) -> None:
    """Send init notification to Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    message = (
        f"🟢 *Arbitrage Bot Started*\n"
        f"Exchanges: {', '.join(exchanges)}\n"
        f"Symbols ({len(symbols)}): {', '.join(symbols)}"
    )

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=message,
        parse_mode="Markdown",
    )


async def send_telegram_signal(signal: Signal) -> None:
    """Send signal notification to Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    message = (
        f"🚨 *{signal.symbol}*\n"
        f"SELL {signal.sell_exchange}: {signal.sell_price}\n"
        f"BUY {signal.buy_exchange}: {signal.buy_price}\n"
        f"Edge: {signal.edge_absolute:.4f} USD ({signal.edge_bps:.2f} bps)"
    )

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=message,
        parse_mode="Markdown",
    )
