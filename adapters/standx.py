"""StandX exchange adapter"""

import time
from decimal import Decimal
from typing import List, Optional, Callable, Awaitable

from core.http.client import HttpClient
from exchanges.standx.perp.rest_client import StandXRestClient

from models import SymbolInfo, FundingRate, FeeRates, MarketUpdate, PriceLevel
from .base import BaseExchangeAdapter


class StandxAdapter(BaseExchangeAdapter):
    """StandX perpetual exchange adapter"""

    name = "standx"
    default_taker_fee = Decimal("0.0004")   # 0.04%
    default_maker_fee = Decimal("0.0001")   # 0.01%

    def __init__(self):
        super().__init__()
        self.http = HttpClient(base_url="https://perps.standx.com", signer=None)
        self.rest = StandXRestClient(http=self.http)
        self.ws: Optional[WsClient] = None
        self._on_update: Optional[Callable[[MarketUpdate], Awaitable[None]]] = None
        self._symbols_cache: dict = {}

    def _normalize_symbol(self, exchange_symbol: str) -> str:
        """Extract base asset from BTC-USD format"""
        parts = exchange_symbol.split("-")
        return parts[0] if parts else exchange_symbol

    async def list_symbols(self) -> List[str]:
        """Fetch all available perp symbols"""
        # StandX has hardcoded symbols in the client
        raw_symbols = self.rest.list_symbols()
        symbols_info = await self.rest.query_symbol_info()

        symbols = []
        for info in symbols_info:
            exc_sym = info.symbol
            normalized = self._normalize_symbol(exc_sym)
            self._symbol_map[normalized] = exc_sym
            self._reverse_map[exc_sym] = normalized
            self._symbols_cache[normalized] = info
            symbols.append(normalized)
        return symbols

    async def get_symbol_info(self, symbol: Optional[str] = None) -> List[SymbolInfo]:
        """Get detailed symbol information"""
        if not self._symbols_cache:
            await self.list_symbols()

        results = []
        for normalized, info in self._symbols_cache.items():
            if symbol and normalized != symbol:
                continue
            results.append(SymbolInfo(
                symbol=normalized,
                exchange_symbol=info.symbol,
                base_asset=info.base_asset,
                quote_asset=info.quote_asset,
                price_decimals=info.price_tick_decimals,
                size_decimals=info.qty_tick_decimals,
                min_size=Decimal(info.min_order_qty),
                max_size=Decimal(info.max_order_qty),
                max_leverage=Decimal(info.max_leverage),
                is_active=info.status == "ACTIVE",
            ))
        return results

    async def get_funding_rate(self, symbol: str) -> FundingRate:
        """Get current funding rate for a symbol"""
        exc_sym = self._symbol_map.get(symbol, symbol)
        market = await self.rest.query_symbol_market(symbol=exc_sym)

        return FundingRate(
            symbol=symbol,
            funding_rate=Decimal(market.funding_rate),
            mark_price=Decimal(market.mark_price),
            index_price=Decimal(market.index_price),
            timestamp=int(time.time() * 1000),
        )

    async def get_fee_rates(self) -> FeeRates:
        """Get fee rates from symbol info"""
        if not self._symbols_cache:
            await self.list_symbols()

        # StandX provides fees per symbol, use first one as default
        for info in self._symbols_cache.values():
            return FeeRates(
                maker_fee=Decimal(info.maker_fee),
                taker_fee=Decimal(info.taker_fee),
            )
        return FeeRates(
            maker_fee=self.default_maker_fee,
            taker_fee=self.default_taker_fee,
        )

    async def subscribe_market_data(
        self,
        symbols: List[str],
        on_update: Callable[[MarketUpdate], Awaitable[None]]
    ) -> None:
        """Subscribe to real-time depth book data"""
        self._on_update = on_update

        async def handle_message(data):
            if not isinstance(data, dict):
                return

            channel = data.get("channel", "")
            if channel != "depth_book":
                return

            exc_sym = data.get("symbol", "")
            if exc_sym not in self._reverse_map:
                return

            book_data = data.get("data", {})
            bids = book_data.get("bids", [])
            asks = book_data.get("asks", [])
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
                ts_exchange=book_data.get("timestamp"),
                ts_local=int(time.time() * 1000),
            )
            await self._on_update(update)

        from exchanges.standx.perp import StandXMarketWsClient
        import asyncio
        self.ws = StandXMarketWsClient(on_message=handle_message)

        # Start connect in background, wait for ready, then subscribe
        asyncio.create_task(self.ws.connect())
        for _ in range(50):  # 5 second timeout
            if self.ws.ws is not None:
                break
            await asyncio.sleep(0.1)
        exc_syms = [self._symbol_map.get(sym, sym) for sym in symbols]
        await self.ws.subscribe_depth_book(exc_syms)

    async def close(self) -> None:
        """Close all connections"""
        if self.ws:
            await self.ws.close()
        await self.http.close()
