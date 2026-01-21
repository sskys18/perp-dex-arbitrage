"""Paradex exchange adapter"""

import time
from decimal import Decimal
from typing import List, Optional, Callable, Awaitable

from core.http.client import HttpClient
from exchanges.paradex.perp.rest_client import ParadexPerpRestClient
from exchanges.paradex.perp.ws_client import ParadexPerpWsClient

from models import SymbolInfo, FundingRate, FeeRates, MarketUpdate, PriceLevel
from .base import BaseExchangeAdapter


class ParadexAdapter(BaseExchangeAdapter):
    """Paradex perpetual exchange adapter"""

    name = "paradex"
    default_taker_fee = Decimal("0.0004")   # 0.04%
    default_maker_fee = Decimal("0.0002")   # 0.02%

    def __init__(self):
        super().__init__()
        self.http = HttpClient(base_url="https://api.prod.paradex.trade/v1", signer=None)
        self.rest = ParadexPerpRestClient(http=self.http)
        self.ws: Optional[ParadexPerpWsClient] = None
        self._on_update: Optional[Callable[[MarketUpdate], Awaitable[None]]] = None
        self._markets_cache: dict = {}

    def _normalize_symbol(self, exchange_symbol: str) -> str:
        """Extract base asset from BTC-USD-PERP format"""
        parts = exchange_symbol.split("-")
        return parts[0] if parts else exchange_symbol

    async def list_symbols(self) -> List[str]:
        """Fetch all available perp symbols"""
        response = await self.rest.get_markets()
        markets = response.get("results", []) if isinstance(response, dict) else response
        symbols = []
        for market in markets:
            exc_sym = market.get("symbol", "")
            if not exc_sym.endswith("-PERP"):
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
            results.append(SymbolInfo(
                symbol=normalized,
                exchange_symbol=market.get("symbol", ""),
                base_asset=market.get("base_currency", normalized),
                quote_asset=market.get("quote_currency", "USD"),
                price_decimals=int(market.get("price_tick_size", "0.01").count("0") + 1) if "." in str(market.get("price_tick_size", "0.01")) else 2,
                size_decimals=int(market.get("quantity_step_size", "0.001").count("0") + 1) if "." in str(market.get("quantity_step_size", "0.001")) else 3,
                min_size=Decimal(str(market.get("min_order_size", "0"))) if market.get("min_order_size") else None,
                max_size=Decimal(str(market.get("max_order_size", "0"))) if market.get("max_order_size") else None,
                is_active=market.get("status") == "active",
            ))
        return results

    async def get_funding_rate(self, symbol: str) -> FundingRate:
        """Get current funding rate for a symbol"""
        exc_sym = self._symbol_map.get(symbol, symbol)
        response = await self.rest.get_funding_data(market=exc_sym)
        data_list = response.get("results", []) if isinstance(response, dict) else response

        if not data_list:
            raise ValueError(f"No funding data for {symbol}")

        data = data_list[0] if isinstance(data_list, list) else data_list
        return FundingRate(
            symbol=symbol,
            funding_rate=Decimal(str(data.get("funding_rate", "0"))),
            mark_price=Decimal(str(data.get("mark_price", "0"))) if data.get("mark_price") else None,
            index_price=Decimal(str(data.get("index_price", "0"))) if data.get("index_price") else None,
            timestamp=int(time.time() * 1000),
        )

    async def get_fee_rates(self) -> FeeRates:
        """Get fee rates (default, requires auth for user-specific)"""
        return FeeRates(
            maker_fee=self.default_maker_fee,
            taker_fee=self.default_taker_fee,
        )

    async def subscribe_market_data(
        self,
        symbols: List[str],
        on_update: Callable[[MarketUpdate], Awaitable[None]]
    ) -> None:
        """Subscribe to real-time BBO data"""
        self._on_update = on_update

        async def handle_message(data):
            if not isinstance(data, dict):
                return

            # Handle JSONRPC format
            params = data.get("params", {})
            channel = params.get("channel", "")
            if not channel.startswith("bbo."):
                return

            bbo_data = params.get("data", {})
            exc_sym = channel.replace("bbo.", "")
            if exc_sym not in self._reverse_map:
                return

            bid = bbo_data.get("bid")
            ask = bbo_data.get("ask")
            if not bid or not ask:
                return

            update = MarketUpdate(
                exchange=self.name,
                symbol=self._reverse_map[exc_sym],
                bid_px=Decimal(str(bid.get("price", "0"))),
                bid_sz=Decimal(str(bid.get("size", "0"))),
                ask_px=Decimal(str(ask.get("price", "0"))),
                ask_sz=Decimal(str(ask.get("size", "0"))),
                ts_exchange=bbo_data.get("timestamp"),
                ts_local=int(time.time() * 1000),
            )
            await self._on_update(update)

        self.ws = ParadexPerpWsClient(on_message=handle_message)

        # Subscribe after connection
        async def on_connect():
            for sym in symbols:
                exc_sym = self._symbol_map.get(sym, sym)
                await self.ws.subscribe_bbo(exc_sym)

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
