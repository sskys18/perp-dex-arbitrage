"""State engine for managing market data"""

import time
from typing import Dict, Optional
from decimal import Decimal

from models import MarketUpdate


class Quote:
    """Represents a quote from a single exchange"""
    __slots__ = ('bid_px', 'bid_sz', 'ask_px', 'ask_sz', 'ts_local', 'ts_exchange')

    def __init__(self, bid_px: Decimal, bid_sz: Decimal, ask_px: Decimal, ask_sz: Decimal, ts_local: int, ts_exchange: Optional[int] = None):
        self.bid_px = bid_px
        self.bid_sz = bid_sz
        self.ask_px = ask_px
        self.ask_sz = ask_sz
        self.ts_local = ts_local
        self.ts_exchange = ts_exchange

    def is_valid(self, max_age_ms: int, now_ms: Optional[int] = None) -> bool:
        """Check if quote is fresh enough"""
        if now_ms is None:
            now_ms = int(time.time() * 1000)
        return (now_ms - self.ts_local) < max_age_ms


class StateEngine:
    """Manages market data state across all exchanges"""

    def __init__(self, max_quote_age_ms: int = 2000):
        self.max_quote_age_ms = max_quote_age_ms
        # quotes[symbol][exchange] = Quote
        self._quotes: Dict[str, Dict[str, Quote]] = {}

    def update(self, update: MarketUpdate) -> None:
        """Process a market data update"""
        symbol = update.symbol
        exchange = update.exchange

        if symbol not in self._quotes:
            self._quotes[symbol] = {}

        self._quotes[symbol][exchange] = Quote(
            bid_px=update.bid_px,
            bid_sz=update.bid_sz,
            ask_px=update.ask_px,
            ask_sz=update.ask_sz,
            ts_local=update.ts_local,
            ts_exchange=update.ts_exchange,
        )

    def get_quote(self, symbol: str, exchange: str, now_ms: Optional[int] = None) -> Optional[Quote]:
        """Get current quote for symbol on exchange"""
        quotes = self._quotes.get(symbol, {})
        quote = quotes.get(exchange)
        if quote and quote.is_valid(self.max_quote_age_ms, now_ms=now_ms):
            return quote
        return None

    def get_all_quotes(self, symbol: str, now_ms: Optional[int] = None) -> Dict[str, Quote]:
        """Get all valid quotes for a symbol across exchanges"""
        quotes = self._quotes.get(symbol, {})
        if now_ms is None:
            now_ms = int(time.time() * 1000)
        return {
            exchange: quote
            for exchange, quote in quotes.items()
            if quote.is_valid(self.max_quote_age_ms, now_ms=now_ms)
        }

    def get_exchanges_for_symbol(self, symbol: str, now_ms: Optional[int] = None) -> list:
        """Get list of exchanges with valid quotes for a symbol"""
        return list(self.get_all_quotes(symbol, now_ms=now_ms).keys())
