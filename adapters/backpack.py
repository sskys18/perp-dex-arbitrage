"""Backpack exchange adapter"""

import time
from decimal import Decimal
from typing import List, Optional, Callable, Awaitable

from core.http.client import HttpClient
from exchanges.backpack.perp.rest_client import BackpackRestClient
from exchanges.backpack.perp.ws_client import BackpackWsClient

from models import SymbolInfo, FundingRate, FeeRates, MarketUpdate, PriceLevel
from .base import BaseExchangeAdapter


class BackpackAdapter(BaseExchangeAdapter):
    """Backpack perpetual exchange adapter"""

    name = "backpack"
    default_taker_fee = Decimal("0.0005")   # 0.05%
    default_maker_fee = Decimal("0.0002")   # 0.02%

    def __init__(self):
        super().__init__()
        self.http = HttpClient(base_url="https://api.backpack.exchange", signer=None)
        self.rest = BackpackRestClient(http=self.http)
        self.ws: Optional[BackpackWsClient] = None
        self._on_update: Optional[Callable[[MarketUpdate], Awaitable[None]]] = None
        self._markets_cache: dict = {}

    def _normalize_symbol(self, exchange_symbol: str) -> str:
        """Extract base asset from BTC_USDC_PERP format"""
        parts = exchange_symbol.split("_")
        return parts[0] if parts else exchange_symbol

    async def list_symbols(self) -> List[str]:
        """Fetch all available perp symbols"""
        markets = await self.rest.get_markets()
        symbols = []
        for market in markets:
            exc_sym = market.symbol
            if not exc_sym.endswith("_PERP"):
                continue
            normalized = self._normalize_symbol(exc_sym)
            self._symbol_map[normalized] = exc_sym
            self._reverse_map[exc_sym] = normalized
            self._markets_cache[normalized] = market
            symbols.append(normalized)
        return symbols

    async def get_symbol_info(self, symbol: Optional[str] = None) -> List[SymbolInfo]:
        """Get detailed symbol information"""
        if not self._markets_cache:
            await self.list_symbols()

        results = []
        for normalized, market in self._markets_cache.items():
            if symbol and normalized != symbol:
                continue
            filters = market.filters or {}
            results.append(SymbolInfo(
                symbol=normalized,
                exchange_symbol=market.symbol,
                base_asset=market.baseSymbol,
                quote_asset=market.quoteSymbol,
                price_decimals=8,
                size_decimals=4,
                min_size=Decimal(str(filters.get("quantity", {}).get("minQuantity", "0"))) if filters.get("quantity") else None,
                is_active=True,
            ))
        return results

    async def get_funding_rate(self, symbol: str) -> FundingRate:
        """Get current funding rate for a symbol"""
        exc_sym = self._symbol_map.get(symbol, symbol)
        mark_prices = await self.rest.get_mark_prices()

        for mp in mark_prices:
            if mp.symbol == exc_sym:
                return FundingRate(
                    symbol=symbol,
                    funding_rate=Decimal(str(mp.estimatedFundingRate)) if mp.estimatedFundingRate else Decimal("0"),
                    mark_price=Decimal(str(mp.markPrice)),
                    index_price=Decimal(str(mp.indexPrice)) if mp.indexPrice else None,
                    next_funding_time=mp.nextFundingTime,
                    timestamp=int(time.time() * 1000),
                )
        raise ValueError(f"Symbol {symbol} not found")

    async def get_fee_rates(self) -> FeeRates:
        """Get fee rates (default, no public API)"""
        return FeeRates(
            maker_fee=self.default_maker_fee,
            taker_fee=self.default_taker_fee,
        )

    async def subscribe_market_data(
        self,
        symbols: List[str],
        on_update: Callable[[MarketUpdate], Awaitable[None]]
    ) -> None:
        """Subscribe to real-time depth data"""
        self._on_update = on_update

        async def handle_message(data):
            if not isinstance(data, dict):
                return

            stream = data.get("stream", "")
            if not stream.startswith("depth."):
                return

            exc_sym = stream.replace("depth.", "")
            if exc_sym not in self._reverse_map:
                return

            book_data = data.get("data", {})
            bids = book_data.get("b", [])
            asks = book_data.get("a", [])
            if not bids or not asks:
                return

            update = MarketUpdate(
                exchange=self.name,
                symbol=self._reverse_map[exc_sym],
                bid_px=Decimal(str(bids[0][0])),
                bid_sz=Decimal(str(bids[0][1])),
                ask_px=Decimal(str(asks[0][0])),
                ask_sz=Decimal(str(asks[0][1])),
                bid_levels=[PriceLevel(px=Decimal(str(b[0])), sz=Decimal(str(b[1]))) for b in bids[:5]],
                ask_levels=[PriceLevel(px=Decimal(str(a[0])), sz=Decimal(str(a[1]))) for a in asks[:5]],
                ts_local=int(time.time() * 1000),
            )
            await self._on_update(update)

        self.ws = BackpackWsClient(on_message=handle_message)

        # Start connect in background, wait for ready, then subscribe
        import asyncio
        asyncio.create_task(self.ws.connect())
        for _ in range(50):  # 5 second timeout
            if self.ws.ws is not None:
                break
            await asyncio.sleep(0.1)
        for sym in symbols:
            exc_sym = self._symbol_map.get(sym, sym)
            await self.ws.subscribe_depth(exc_sym)

    async def close(self) -> None:
        """Close all connections"""
        if self.ws:
            await self.ws.close()
        await self.http.close()
