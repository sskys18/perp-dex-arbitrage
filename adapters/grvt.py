"""GRVT exchange adapter"""

import time
from decimal import Decimal
from typing import List, Optional, Callable, Awaitable

from core.http.client import HttpClient
from exchanges.grvt.perp.rest_client import GrvtPerpRestClient
from exchanges.grvt.perp.ws_client import GrvtPerpWsClient

from models import SymbolInfo, FundingRate, FeeRates, MarketUpdate, PriceLevel
from .base import BaseExchangeAdapter


class GrvtAdapter(BaseExchangeAdapter):
    """GRVT perpetual exchange adapter"""

    name = "grvt"
    default_taker_fee = Decimal("0.00045")  # 0.045%
    default_maker_fee = Decimal("-0.000001")  # -0.0001% (rebate)

    def __init__(self):
        super().__init__()
        self.http = HttpClient(base_url="https://edge.grvt.io", signer=None)
        self.rest = GrvtPerpRestClient(http=self.http)
        self.ws: Optional[GrvtPerpWsClient] = None
        self._on_update: Optional[Callable[[MarketUpdate], Awaitable[None]]] = None
        self._instruments_cache: dict = {}

    def _normalize_symbol(self, exchange_symbol: str) -> str:
        """Extract base asset from BTC_USDT_Perp format"""
        parts = exchange_symbol.split("_")
        return parts[0] if parts else exchange_symbol

    async def list_symbols(self) -> List[str]:
        """Fetch all available perp symbols"""
        response = await self.rest.get_all_instruments(is_active=True)
        instruments = response.get("result", []) if isinstance(response, dict) else response
        symbols = []
        for inst in instruments:
            exc_sym = inst.get("instrument", "")
            if not exc_sym.endswith("_Perp"):
                continue
            normalized = self._normalize_symbol(exc_sym)
            self._symbol_map[normalized] = exc_sym
            self._reverse_map[exc_sym] = normalized
            self._instruments_cache[normalized] = inst
            symbols.append(normalized)
        return symbols

    async def get_symbol_info(self, symbol: Optional[str] = None) -> List[SymbolInfo]:
        """Get detailed symbol information"""
        if not self._instruments_cache:
            await self.list_symbols()

        results = []
        for normalized, inst in self._instruments_cache.items():
            if symbol and normalized != symbol:
                continue
            results.append(SymbolInfo(
                symbol=normalized,
                exchange_symbol=inst.get("instrument", ""),
                base_asset=inst.get("base", normalized),
                quote_asset=inst.get("quote", "USDT"),
                price_decimals=int(inst.get("tick_size", 2)),
                size_decimals=int(inst.get("min_size_decimals", 4)),
                min_size=Decimal(str(inst.get("min_size", "0"))) if inst.get("min_size") else None,
                max_leverage=Decimal(str(inst.get("max_leverage", "50"))) if inst.get("max_leverage") else None,
                is_active=inst.get("is_active", True),
            ))
        return results

    async def get_funding_rate(self, symbol: str) -> FundingRate:
        """Get current funding rate for a symbol"""
        exc_sym = self._symbol_map.get(symbol, symbol)
        response = await self.rest.get_funding_rate(instrument=exc_sym, limit=1)
        results = response.get("result", []) if isinstance(response, dict) else response

        if not results:
            raise ValueError(f"No funding data for {symbol}")

        data = results[0] if isinstance(results, list) else results
        return FundingRate(
            symbol=symbol,
            funding_rate=Decimal(str(data.get("funding_rate", "0"))),
            mark_price=Decimal(str(data.get("mark_price", "0"))) if data.get("mark_price") else None,
            index_price=Decimal(str(data.get("index_price", "0"))) if data.get("index_price") else None,
            timestamp=int(data.get("event_time", time.time() * 1000)),
        )

    async def get_fee_rates(self) -> FeeRates:
        """Get fee rates (fixed, no public API)"""
        return FeeRates(
            maker_fee=self.default_maker_fee,
            taker_fee=self.default_taker_fee,
        )

    async def subscribe_market_data(
        self,
        symbols: List[str],
        on_update: Callable[[MarketUpdate], Awaitable[None]]
    ) -> None:
        """Subscribe to real-time mini book data"""
        self._on_update = on_update

        async def handle_message(data):
            if not isinstance(data, dict):
                return

            result = data.get("result", {})
            if not result:
                return

            feed = result.get("feed", "")
            if feed != "v1.mini.s":
                return

            mini_data = result.get("data", {})
            exc_sym = mini_data.get("instrument", "")
            if exc_sym not in self._reverse_map:
                return

            bids = mini_data.get("bids", [])
            asks = mini_data.get("asks", [])
            if not bids or not asks:
                return

            update = MarketUpdate(
                exchange=self.name,
                symbol=self._reverse_map[exc_sym],
                bid_px=Decimal(str(bids[0].get("price", "0"))),
                bid_sz=Decimal(str(bids[0].get("size", "0"))),
                ask_px=Decimal(str(asks[0].get("price", "0"))),
                ask_sz=Decimal(str(asks[0].get("size", "0"))),
                bid_levels=[PriceLevel(px=Decimal(str(b.get("price", "0"))), sz=Decimal(str(b.get("size", "0")))) for b in bids[:5]],
                ask_levels=[PriceLevel(px=Decimal(str(a.get("price", "0"))), sz=Decimal(str(a.get("size", "0")))) for a in asks[:5]],
                ts_exchange=mini_data.get("event_time"),
                ts_local=int(time.time() * 1000),
            )
            await self._on_update(update)

        self.ws = GrvtPerpWsClient(on_message=handle_message)

        async def on_connect():
            instruments = [self._symbol_map.get(sym, sym) for sym in symbols]
            await self.ws.subscribe_mini_book(instruments=instruments)

        import asyncio
        connect_task = asyncio.create_task(self.ws.connect())
        await asyncio.sleep(1)
        await on_connect()
        await connect_task

    async def close(self) -> None:
        """Close all connections"""
        if self.ws:
            await self.ws.close()
        await self.http.close()
