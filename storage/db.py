"""SQLite storage for signals"""

import os
import aiosqlite
from models import Signal


SIGNALS_DB_PATH = os.getenv("SIGNALS_DB_PATH", "signals.db")


async def init_db() -> None:
    """Initialize database and create tables"""
    async with aiosqlite.connect(SIGNALS_DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id TEXT UNIQUE,
                symbol TEXT,
                sell_exchange TEXT,
                buy_exchange TEXT,
                qty TEXT,
                sell_price TEXT,
                buy_price TEXT,
                sell_score TEXT,
                buy_score TEXT,
                edge_absolute TEXT,
                edge_bps TEXT,
                sell_fee TEXT,
                buy_fee TEXT,
                sell_funding TEXT,
                buy_funding TEXT,
                created_ts INTEGER
            )
        """)
        await db.commit()


async def save_signal(signal: Signal) -> None:
    """Save signal to database"""
    async with aiosqlite.connect(SIGNALS_DB_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO signals (
                signal_id, symbol, sell_exchange, buy_exchange, qty,
                sell_price, buy_price, sell_score, buy_score,
                edge_absolute, edge_bps, sell_fee, buy_fee,
                sell_funding, buy_funding, created_ts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal.signal_id,
                signal.symbol,
                signal.sell_exchange,
                signal.buy_exchange,
                str(signal.qty),
                str(signal.sell_price),
                str(signal.buy_price),
                str(signal.sell_score),
                str(signal.buy_score),
                str(signal.edge_absolute),
                str(signal.edge_bps),
                str(signal.sell_fee),
                str(signal.buy_fee),
                str(signal.sell_funding),
                str(signal.buy_funding),
                signal.created_ts,
            ),
        )
        await db.commit()
